using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Serialization;
using FinHub.Client.Models.Markets;
using FinHub.Client.Models.Portfolios;
using FinHub.Client.Schemas.MarketIndex;
using Xunit;

namespace FinHub.Client.Contracts.Tests;

public sealed class ComponentContractParityTests
{
    private static readonly NullabilityInfoContext Nullability = new();

    private static readonly IReadOnlySet<string> UnformattedInt64Properties =
        new HashSet<string>(StringComparer.Ordinal)
        {
            "CompanyBriefInfo.market_cap",
            "HistoryPoint.timestamp",
            "HistoryPoint.volume",
            "ListingEvent.timestamp",
            "StockHistory.average_volume_30d",
            "StockHistory.current_volume",
            "StockHistory.yesterday_volume",
            "StockQuote.ask_size",
            "StockQuote.bid_size",
            "StockQuote.market_cap",
            "StockQuote.market_volume",
            "SymbolDividend.ex_dividend_date",
            "SymbolDividend.last_dividend_date",
            "SymbolInfo.ebitda",
            "SymbolInfo.market_cap",
            "SymbolInfo.total_cash",
            "SymbolInfo.total_debt",
            "SymbolInfo.total_revenue",
            "SymbolOverview.ebitda",
            "SymbolOverview.market_cap",
            "SymbolOverview.total_cash",
            "SymbolOverview.total_debt",
            "SymbolOverview.total_revenue",
            "TickerMarketSnapshot.market_cap",
            "TickerMarketSnapshot.market_volume",
            "UpcomingDividendEvent.timestamp",
            "UpcomingEarningsEvent.timestamp",
            "app__models__event__DividendEventAnalysis.avg_dvt_7d",
            "app__models__event__DividendEventAnalysis.avg_volume_30d",
            "app__models__event__DividendEventAnalysis.std_dvt_7d",
            "app__models__event__DividendEventAnalysis.std_volume_30d",
            "app__models__event__DividendEventAnalysis.timestamp",
        };

    [Fact]
    public void Every_client_component_has_an_unambiguous_dotnet_type()
    {
        var errors = new List<string>();
        var mappedTypes = new HashSet<Type>();

        foreach (var component in OpenApiContract.Schemas.EnumerateObject())
        {
            if (ContractMappings.IgnoredOpenApiComponents.Contains(component.Name))
            {
                continue;
            }

            if (
                !ContractMappings.TryResolveComponentType(
                    component.Name,
                    out var contractType
                )
            )
            {
                errors.Add(
                    $"OpenAPI component '{component.Name}' has no unambiguous .NET type."
                );
                continue;
            }

            mappedTypes.Add(contractType!);
        }

        var intentionalNonComponentTypes = new HashSet<Type>
        {
            typeof(GetMarketIndexResponse),
            typeof(MarketIndexConstituent),
        };
        var uncoveredTypes = ContractMappings
            .ContractsAssembly.GetExportedTypes()
            .Where(
                type =>
                    type.IsClass
                    && !type.IsAbstract
                    && !type.Name.EndsWith("JsonConverter", StringComparison.Ordinal)
            )
            .Where(type => !mappedTypes.Contains(type))
            .Where(type => !intentionalNonComponentTypes.Contains(type))
            .OrderBy(type => type.FullName, StringComparer.Ordinal)
            .ToArray();

        foreach (var type in uncoveredTypes)
        {
            errors.Add(
                $".NET contract '{type.FullName}' is not covered by an OpenAPI component mapping."
            );
        }

        AssertNoErrors("Component coverage failures", errors);
    }

    [Fact]
    public void Object_properties_match_names_requiredness_nullability_and_types()
    {
        var errors = new List<string>();

        foreach (var component in OpenApiContract.Schemas.EnumerateObject())
        {
            if (ContractMappings.IgnoredOpenApiComponents.Contains(component.Name))
            {
                continue;
            }

            var contractType = ContractMappings.ResolveComponentType(component.Name);
            CompareObjectComponent(component.Name, component.Value, contractType, errors);
        }

        AssertNoErrors("OpenAPI object parity failures", errors);
    }

    [Fact]
    public void Enum_converters_round_trip_every_exact_OpenAPI_wire_value()
    {
        var errors = new List<string>();
        var enumCases = new Dictionary<Type, (HashSet<string> Values, List<string> Paths)>();

        foreach (var component in OpenApiContract.Schemas.EnumerateObject())
        {
            if (ContractMappings.IgnoredOpenApiComponents.Contains(component.Name))
            {
                continue;
            }

            var contractType = ContractMappings.ResolveComponentType(component.Name);
            var properties = GetPropertiesByJsonName(contractType, errors);
            foreach (var propertySchema in component.Value.GetProperty("properties").EnumerateObject())
            {
                var expectedValues = OpenApiContract.GetEnumStrings(propertySchema.Value);
                if (expectedValues.Count == 0)
                {
                    continue;
                }

                var path = $"{component.Name}.{propertySchema.Name}";
                if (!properties.TryGetValue(propertySchema.Name, out var property))
                {
                    errors.Add($"{path}: no matching .NET property exists.");
                    continue;
                }

                var enumType = Nullable.GetUnderlyingType(property.PropertyType)
                    ?? property.PropertyType;
                if (!enumType.IsEnum)
                {
                    errors.Add(
                        $"{path}: OpenAPI declares enum values, but .NET type is "
                            + $"'{FormatType(enumType)}'."
                    );
                    continue;
                }

                if (!enumCases.TryGetValue(enumType, out var enumCase))
                {
                    enumCase = (
                        new HashSet<string>(expectedValues, StringComparer.Ordinal),
                        []
                    );
                    enumCases.Add(enumType, enumCase);
                }
                else if (!enumCase.Values.SetEquals(expectedValues))
                {
                    errors.Add(
                        $"{path}: enum wire values differ from other uses of "
                            + $"'{enumType.FullName}'."
                    );
                }

                enumCase.Paths.Add(path);
            }
        }

        var publicEnums = ContractMappings
            .ContractsAssembly.GetExportedTypes()
            .Where(type => type.IsEnum)
            .ToHashSet();
        foreach (var uncoveredEnum in publicEnums.Except(enumCases.Keys))
        {
            errors.Add(
                $".NET enum '{uncoveredEnum.FullName}' is not exercised by an OpenAPI enum."
            );
        }

        foreach (var (enumType, enumCase) in enumCases)
        {
            var context = string.Join(", ", enumCase.Paths.Order(StringComparer.Ordinal));
            var actualValues = new HashSet<string>(StringComparer.Ordinal);

            foreach (var value in Enum.GetValues(enumType).Cast<object>())
            {
                try
                {
                    var json = JsonSerializer.Serialize(value, enumType);
                    var wireValue = JsonSerializer.Deserialize<string>(json);
                    if (wireValue is null)
                    {
                        errors.Add(
                            $"{context}: '{enumType.FullName}' serialized to non-string JSON {json}."
                        );
                    }
                    else
                    {
                        actualValues.Add(wireValue);
                    }
                }
                catch (Exception exception)
                {
                    errors.Add(
                        $"{context}: failed to serialize '{enumType.FullName}': "
                            + exception.Message
                    );
                }
            }

            if (!actualValues.SetEquals(enumCase.Values))
            {
                errors.Add(
                    $"{context}: '{enumType.FullName}' serializes as "
                        + $"{FormatValues(actualValues)}, expected "
                        + $"{FormatValues(enumCase.Values)}."
                );
            }

            foreach (var wireValue in enumCase.Values)
            {
                try
                {
                    var value = JsonSerializer.Deserialize(
                        JsonSerializer.Serialize(wireValue),
                        enumType
                    );
                    var roundTrip = JsonSerializer.Deserialize<string>(
                        JsonSerializer.Serialize(value, enumType)
                    );
                    if (roundTrip != wireValue)
                    {
                        errors.Add(
                            $"{context}: '{enumType.FullName}' wire value '{wireValue}' "
                                + $"round-tripped as '{roundTrip}'."
                        );
                    }
                }
                catch (Exception exception)
                {
                    errors.Add(
                        $"{context}: '{enumType.FullName}' could not read wire value "
                            + $"'{wireValue}': {exception.Message}"
                    );
                }
            }

            try
            {
                JsonSerializer.Deserialize("\"__UNKNOWN_OPENAPI_ENUM_VALUE__\"", enumType);
                errors.Add(
                    $"{context}: '{enumType.FullName}' accepted an unknown string value."
                );
            }
            catch (JsonException)
            {
                // Unknown string values are intentionally rejected.
            }
        }

        AssertNoErrors("Enum wire-value parity failures", errors);
    }

    private static void CompareObjectComponent(
        string componentName,
        JsonElement schema,
        Type contractType,
        ICollection<string> errors
    )
    {
        var schemaTypeName =
            schema.TryGetProperty("type", out var schemaType)
            && schemaType.ValueKind == JsonValueKind.String
                ? schemaType.GetString()
                : null;
        if (schemaTypeName != "object")
        {
            errors.Add(
                $"{componentName}: expected an OpenAPI object schema, found "
                    + $"'{schemaTypeName ?? "<missing>"}'."
            );
            return;
        }

        var properties = GetPropertiesByJsonName(contractType, errors);
        var schemaProperties = schema
            .GetProperty("properties")
            .EnumerateObject()
            .ToDictionary(property => property.Name, property => property.Value);
        var required = schema
            .TryGetProperty("required", out var requiredElement)
            ? requiredElement
                .EnumerateArray()
                .Select(value => value.GetString()!)
                .ToHashSet(StringComparer.Ordinal)
            : new HashSet<string>(StringComparer.Ordinal);

        foreach (
            var missing in schemaProperties.Keys.Except(
                properties.Keys,
                StringComparer.Ordinal
            )
        )
        {
            errors.Add(
                $"{componentName}.{missing}: OpenAPI property has no .NET property."
            );
        }

        foreach (
            var extra in properties.Keys.Except(
                schemaProperties.Keys,
                StringComparer.Ordinal
            )
        )
        {
            errors.Add(
                $"{componentName}.{extra}: .NET property is absent from OpenAPI."
            );
        }

        foreach (var (jsonName, property) in properties)
        {
            if (!schemaProperties.TryGetValue(jsonName, out var propertySchema))
            {
                continue;
            }

            var path = $"{componentName}.{jsonName}";
            var isRequired = property.IsDefined(
                typeof(RequiredMemberAttribute),
                inherit: true
            );
            if (isRequired != required.Contains(jsonName))
            {
                errors.Add(
                    $"{path}: .NET required={isRequired}, "
                        + $"OpenAPI required={required.Contains(jsonName)}."
                );
            }

            var isNullable =
                Nullable.GetUnderlyingType(property.PropertyType) is not null
                || Nullability.Create(property).ReadState == NullabilityState.Nullable;
            var openApiNullable = OpenApiContract.AllowsNull(propertySchema);
            if (isNullable != openApiNullable)
            {
                errors.Add(
                    $"{path}: .NET nullable={isNullable}, "
                        + $"OpenAPI nullable={openApiNullable}."
                );
            }

            ComparePropertyType(
                path,
                propertySchema,
                property.PropertyType,
                errors
            );
        }
    }

    private static Dictionary<string, PropertyInfo> GetPropertiesByJsonName(
        Type contractType,
        ICollection<string> errors
    )
    {
        var properties = new Dictionary<string, PropertyInfo>(StringComparer.Ordinal);

        foreach (var property in contractType.GetProperties(BindingFlags.Instance | BindingFlags.Public))
        {
            var attribute = property.GetCustomAttribute<JsonPropertyNameAttribute>(
                inherit: true
            );
            if (attribute is null)
            {
                errors.Add(
                    $"{contractType.FullName}.{property.Name}: public serialized property "
                        + "has no JsonPropertyNameAttribute."
                );
                continue;
            }

            if (!properties.TryAdd(attribute.Name, property))
            {
                errors.Add(
                    $"{contractType.FullName}: duplicate JSON property name "
                        + $"'{attribute.Name}'."
                );
            }
        }

        return properties;
    }

    private static void ComparePropertyType(
        string path,
        JsonElement schema,
        Type propertyType,
        ICollection<string> errors
    )
    {
        var actualType = Nullable.GetUnderlyingType(propertyType) ?? propertyType;
        var alternatives = OpenApiContract.GetNonNullAlternatives(schema);
        if (alternatives.Count != 1)
        {
            errors.Add(
                $"{path}: unsupported OpenAPI union with {alternatives.Count} "
                    + "non-null alternatives."
            );
            return;
        }

        schema = alternatives[0];

        if (schema.TryGetProperty("oneOf", out var union))
        {
            var references = OpenApiContract.GetSchemaReferences(union);
            var expectedReferences = new HashSet<string>(StringComparer.Ordinal)
            {
                "PortfolioConstruction",
                "PortfolioReview",
            };
            if (
                actualType != typeof(IPortfolioAnalysisResult)
                || !references.SetEquals(expectedReferences)
            )
            {
                errors.Add(
                    $"{path}: discriminated union is '{FormatType(actualType)}' over "
                        + $"{FormatValues(references)}, expected "
                        + $"'{typeof(IPortfolioAnalysisResult).FullName}' over "
                        + $"{FormatValues(expectedReferences)}."
                );
            }

            if (
                !schema.TryGetProperty("discriminator", out var discriminator)
                || discriminator.GetProperty("propertyName").GetString() != "result_type"
            )
            {
                errors.Add(
                    $"{path}: portfolio union discriminator must be 'result_type'."
                );
            }

            return;
        }

        if (schema.TryGetProperty("$ref", out var reference))
        {
            var componentName = reference.GetString()!.Split('/')[^1];
            CompareExpectedType(
                path,
                ContractMappings.ResolveComponentType(componentName),
                actualType,
                errors
            );
            return;
        }

        var enumValues = OpenApiContract.GetEnumStrings(schema);
        if (enumValues.Count > 0)
        {
            if (!actualType.IsEnum)
            {
                errors.Add(
                    $"{path}: OpenAPI enum maps to '{FormatType(actualType)}', "
                        + "expected a .NET enum."
                );
            }

            return;
        }

        if (!schema.TryGetProperty("type", out var typeElement))
        {
            CompareExpectedType(path, typeof(JsonElement), actualType, errors);
            return;
        }

        switch (typeElement.GetString())
        {
            case "array":
                if (
                    !actualType.IsGenericType
                    || actualType.GetGenericTypeDefinition() != typeof(IReadOnlyList<>)
                )
                {
                    errors.Add(
                        $"{path}: OpenAPI array maps to '{FormatType(actualType)}', "
                            + "expected IReadOnlyList<T>."
                    );
                    return;
                }

                ComparePropertyType(
                    $"{path}[]",
                    schema.GetProperty("items"),
                    actualType.GetGenericArguments()[0],
                    errors
                );
                break;
            case "boolean":
                CompareExpectedType(path, typeof(bool), actualType, errors);
                break;
            case "integer":
                var integerFormat =
                    schema.TryGetProperty("format", out var integerFormatElement)
                        ? integerFormatElement.GetString()
                        : null;
                var expectedIntegerType =
                    integerFormat == "int64" || UnformattedInt64Properties.Contains(path)
                        ? typeof(long)
                        : typeof(int);
                CompareExpectedType(path, expectedIntegerType, actualType, errors);
                break;
            case "number":
                CompareExpectedType(path, typeof(double), actualType, errors);
                break;
            case "object":
                if (!schema.TryGetProperty("additionalProperties", out var valueSchema))
                {
                    errors.Add(
                        $"{path}: unsupported inline OpenAPI object without "
                            + "additionalProperties."
                    );
                    return;
                }

                if (
                    !actualType.IsGenericType
                    || actualType.GetGenericTypeDefinition()
                        != typeof(IReadOnlyDictionary<,>)
                    || actualType.GetGenericArguments()[0] != typeof(string)
                )
                {
                    errors.Add(
                        $"{path}: OpenAPI string-keyed object maps to "
                            + $"'{FormatType(actualType)}', expected "
                            + "IReadOnlyDictionary<string, TValue>."
                    );
                    return;
                }

                ComparePropertyType(
                    $"{path}{{value}}",
                    valueSchema,
                    actualType.GetGenericArguments()[1],
                    errors
                );
                break;
            case "string":
                var format =
                    schema.TryGetProperty("format", out var formatElement)
                        ? formatElement.GetString()
                        : null;
                var expectedStringType = format switch
                {
                    "date" => typeof(DateOnly),
                    "date-time" => typeof(DateTimeOffset),
                    "uri" => typeof(Uri),
                    null => typeof(string),
                    _ => null,
                };

                if (expectedStringType is null)
                {
                    errors.Add($"{path}: unsupported OpenAPI string format '{format}'.");
                }
                else
                {
                    CompareExpectedType(path, expectedStringType, actualType, errors);
                }

                break;
            default:
                errors.Add(
                    $"{path}: unsupported OpenAPI type '{typeElement.GetString()}'."
                );
                break;
        }
    }

    private static void CompareExpectedType(
        string path,
        Type expected,
        Type actual,
        ICollection<string> errors
    )
    {
        if (expected != actual)
        {
            errors.Add(
                $"{path}: .NET type is '{FormatType(actual)}', "
                    + $"expected '{FormatType(expected)}'."
            );
        }
    }

    private static void AssertNoErrors(string heading, IReadOnlyCollection<string> errors)
    {
        Assert.True(
            errors.Count == 0,
            heading
                + ":"
                + Environment.NewLine
                + string.Join(Environment.NewLine, errors.Select(error => $"- {error}"))
        );
    }

    private static string FormatType(Type type) => type.FullName ?? type.Name;

    private static string FormatValues(IEnumerable<string> values)
    {
        var materialized = values.Order(StringComparer.Ordinal).ToArray();
        return materialized.Length == 0 ? "<none>" : string.Join(", ", materialized);
    }
}
