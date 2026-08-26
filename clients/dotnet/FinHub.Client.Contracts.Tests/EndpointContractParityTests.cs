using System.Text.Json;
using FinHub.Client.Schemas;
using FinHub.Client.Schemas.MarketIndex;
using Xunit;

namespace FinHub.Client.Contracts.Tests;

public sealed class EndpointContractParityTests
{
    [Fact]
    public void Every_public_router_operation_has_an_explicit_contract_mapping()
    {
        var actual = OpenApiContract
            .GetOperations()
            .Where(operation => operation.Path is not "/" and not "/health")
            .Select(FormatOperation)
            .ToHashSet(StringComparer.Ordinal);
        var expected = ContractMappings
            .Endpoints.Select(endpoint => FormatOperation((endpoint.Method, endpoint.Path)))
            .ToHashSet(StringComparer.Ordinal);

        var missing = actual.Except(expected).Order(StringComparer.Ordinal).ToArray();
        var stale = expected.Except(actual).Order(StringComparer.Ordinal).ToArray();

        Assert.True(
            missing.Length == 0 && stale.Length == 0,
            $"Public operation coverage drifted.{Environment.NewLine}"
                + $"Missing mappings: {FormatValues(missing)}{Environment.NewLine}"
                + $"Stale mappings: {FormatValues(stale)}"
        );
    }

    [Fact]
    public void Endpoint_request_and_response_mappings_match_OpenAPI()
    {
        var errors = new List<string>();
        var paths = OpenApiContract.Root.GetProperty("paths");

        foreach (var endpoint in ContractMappings.Endpoints)
        {
            var operationName = $"{endpoint.Method} {endpoint.Path}";
            if (!paths.TryGetProperty(endpoint.Path, out var path))
            {
                errors.Add($"{operationName}: path is absent from openapi.json.");
                continue;
            }

            if (!path.TryGetProperty(endpoint.Method.ToLowerInvariant(), out var operation))
            {
                errors.Add($"{operationName}: method is absent from openapi.json.");
                continue;
            }

            CompareRequest(endpoint, operation, errors);
            CompareResponse(endpoint, operation, errors);
        }

        Assert.True(
            errors.Count == 0,
            "Endpoint contract parity failures:"
                + Environment.NewLine
                + string.Join(Environment.NewLine, errors.Select(error => $"- {error}"))
        );
    }

    private static void CompareRequest(
        EndpointContract endpoint,
        JsonElement operation,
        ICollection<string> errors
    )
    {
        var operationName = $"{endpoint.Method} {endpoint.Path}";
        var hasRequestBody = operation.TryGetProperty("requestBody", out var requestBody);

        if (endpoint.RequestType is null || endpoint.RequestComponent is null)
        {
            if (hasRequestBody)
            {
                errors.Add(
                    $"{operationName}: OpenAPI defines a request body, but the mapping expects none."
                );
            }

            return;
        }

        if (!hasRequestBody)
        {
            errors.Add(
                $"{operationName}: expected request component "
                    + $"'{endpoint.RequestComponent}', but OpenAPI has no request body."
            );
            return;
        }

        var isRequired =
            requestBody.TryGetProperty("required", out var required)
            && required.ValueKind == JsonValueKind.True;
        if (isRequired != endpoint.RequestBodyRequired)
        {
            errors.Add(
                $"{operationName}: request-body requiredness is {isRequired}, "
                    + $"expected {endpoint.RequestBodyRequired}."
            );
        }

        if (
            !requestBody.TryGetProperty("content", out var content)
            || !content.TryGetProperty("application/json", out var jsonContent)
            || !jsonContent.TryGetProperty("schema", out var schema)
        )
        {
            errors.Add($"{operationName}: request body has no application/json schema.");
            return;
        }

        var references = OpenApiContract.GetSchemaReferences(schema);
        if (!references.Contains(endpoint.RequestComponent))
        {
            errors.Add(
                $"{operationName}: request schema references {FormatValues(references)}, "
                    + $"expected '{endpoint.RequestComponent}'."
            );
        }

        if (!endpoint.RequestBodyRequired && !OpenApiContract.AllowsNull(schema))
        {
            errors.Add(
                $"{operationName}: optional async start/poll request must allow a null body."
            );
        }

        var mappedType = ContractMappings.ResolveComponentType(endpoint.RequestComponent);
        if (mappedType != endpoint.RequestType)
        {
            errors.Add(
                $"{operationName}: request component '{endpoint.RequestComponent}' maps to "
                    + $"'{mappedType.FullName}', expected '{endpoint.RequestType.FullName}'."
            );
        }
    }

    private static void CompareResponse(
        EndpointContract endpoint,
        JsonElement operation,
        ICollection<string> errors
    )
    {
        var operationName = $"{endpoint.Method} {endpoint.Path}";
        var successfulSchemas = GetSuccessfulJsonSchemas(operation).ToArray();

        if (endpoint.EnvelopeKind == ResponseEnvelopeKind.Raw)
        {
            if (successfulSchemas.Length != 0)
            {
                errors.Add(
                    $"{operationName}: raw market-index response unexpectedly gained "
                        + "a declared OpenAPI success schema; add an explicit parity mapping."
                );
            }

            if (endpoint.ResponseType != typeof(GetMarketIndexResponse))
            {
                errors.Add(
                    $"{operationName}: raw response must map to "
                        + $"'{typeof(GetMarketIndexResponse).FullName}'."
                );
            }

            if (
                HasGenericBase(endpoint.ResponseType, typeof(ApiResponse<>))
                || HasGenericBase(endpoint.ResponseType, typeof(AsyncApiResponse<>))
            )
            {
                errors.Add(
                    $"{operationName}: raw market-index response must not use an API envelope."
                );
            }

            return;
        }

        if (endpoint.ResponseComponent is null)
        {
            errors.Add($"{operationName}: envelope response has no component mapping.");
            return;
        }

        if (successfulSchemas.Length == 0)
        {
            errors.Add($"{operationName}: OpenAPI has no application/json success response.");
            return;
        }

        foreach (var (statusCode, schema) in successfulSchemas)
        {
            var references = OpenApiContract.GetSchemaReferences(schema);
            if (!references.Contains(endpoint.ResponseComponent))
            {
                errors.Add(
                    $"{operationName} response {statusCode}: schema references "
                        + $"{FormatValues(references)}, expected '{endpoint.ResponseComponent}'."
                );
            }
        }

        var mappedType = ContractMappings.ResolveComponentType(endpoint.ResponseComponent);
        if (mappedType != endpoint.ResponseType)
        {
            errors.Add(
                $"{operationName}: response component '{endpoint.ResponseComponent}' maps to "
                    + $"'{mappedType.FullName}', expected '{endpoint.ResponseType.FullName}'."
            );
        }

        CompareEnvelope(endpoint, errors);
    }

    private static void CompareEnvelope(
        EndpointContract endpoint,
        ICollection<string> errors
    )
    {
        var operationName = $"{endpoint.Method} {endpoint.Path}";
        var schema = OpenApiContract.GetSchema(endpoint.ResponseComponent!);
        var properties = schema.GetProperty("properties");
        var required = schema.TryGetProperty("required", out var requiredElement)
            ? requiredElement
                .EnumerateArray()
                .Select(value => value.GetString()!)
                .ToHashSet(StringComparer.Ordinal)
            : new HashSet<string>(StringComparer.Ordinal);

        if (!properties.TryGetProperty("extra", out var extra))
        {
            errors.Add(
                $"{operationName}: response component '{endpoint.ResponseComponent}' "
                    + "does not expose 'extra'."
            );
            return;
        }

        if (endpoint.EnvelopeKind == ResponseEnvelopeKind.Asynchronous)
        {
            if (!HasGenericBase(endpoint.ResponseType, typeof(AsyncApiResponse<>)))
            {
                errors.Add(
                    $"{operationName}: async response '{endpoint.ResponseType.FullName}' "
                        + "does not derive from AsyncApiResponse<T>."
                );
            }

            if (!required.Contains("extra"))
            {
                errors.Add(
                    $"{operationName}: async response metadata 'extra' is not required."
                );
            }

            var references = OpenApiContract.GetSchemaReferences(extra);
            if (!references.SetEquals(["AsyncTaskInfo"]))
            {
                errors.Add(
                    $"{operationName}: async 'extra' references {FormatValues(references)}, "
                        + "expected only 'AsyncTaskInfo'."
                );
            }
        }
        else
        {
            if (!HasGenericBase(endpoint.ResponseType, typeof(ApiResponseWithExtra<>)))
            {
                errors.Add(
                    $"{operationName}: synchronous response '{endpoint.ResponseType.FullName}' "
                        + "does not derive from ApiResponseWithExtra<T>."
                );
            }

            if (required.Contains("extra") || !OpenApiContract.AllowsNull(extra))
            {
                errors.Add(
                    $"{operationName}: synchronous 'extra' must be optional and nullable."
                );
            }
        }
    }

    private static IEnumerable<(string StatusCode, JsonElement Schema)>
        GetSuccessfulJsonSchemas(JsonElement operation)
    {
        foreach (var response in operation.GetProperty("responses").EnumerateObject())
        {
            if (
                response.Name.Length != 3
                || response.Name[0] != '2'
                || !response.Value.TryGetProperty("content", out var content)
                || !content.TryGetProperty("application/json", out var jsonContent)
                || !jsonContent.TryGetProperty("schema", out var schema)
            )
            {
                continue;
            }

            yield return (response.Name, schema);
        }
    }

    private static bool HasGenericBase(Type type, Type genericTypeDefinition)
    {
        for (var current = type; current is not null; current = current.BaseType)
        {
            if (
                current.IsGenericType
                && current.GetGenericTypeDefinition() == genericTypeDefinition
            )
            {
                return true;
            }
        }

        return false;
    }

    private static string FormatOperation((string Method, string Path) operation) =>
        $"{operation.Method} {operation.Path}";

    private static string FormatValues(IEnumerable<string> values)
    {
        var materialized = values.Order(StringComparer.Ordinal).ToArray();
        return materialized.Length == 0 ? "<none>" : string.Join(", ", materialized);
    }
}
