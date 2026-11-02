using System.Text.Json;

namespace FinHub.Client.Contracts.Tests;

internal static class OpenApiContract
{
    private static readonly HashSet<string> HttpMethods =
    [
        "delete",
        "get",
        "head",
        "options",
        "patch",
        "post",
        "put",
        "trace",
    ];

    private static readonly JsonDocument Document = LoadDocument();

    public static JsonElement Root => Document.RootElement;

    public static JsonElement Schemas =>
        Root.GetProperty("components").GetProperty("schemas");

    public static JsonElement GetSchema(string componentName)
    {
        if (!Schemas.TryGetProperty(componentName, out var schema))
        {
            throw new InvalidOperationException(
                $"OpenAPI component '{componentName}' does not exist."
            );
        }

        return schema;
    }

    public static IEnumerable<(string Method, string Path)> GetOperations()
    {
        foreach (var path in Root.GetProperty("paths").EnumerateObject())
        {
            foreach (var operation in path.Value.EnumerateObject())
            {
                if (HttpMethods.Contains(operation.Name))
                {
                    yield return (operation.Name.ToUpperInvariant(), path.Name);
                }
            }
        }
    }

    public static bool AllowsNull(JsonElement schema)
    {
        if (
            schema.ValueKind == JsonValueKind.Object
            && schema.TryGetProperty("type", out var type)
            && type.ValueKind == JsonValueKind.String
            && type.GetString() == "null"
        )
        {
            return true;
        }

        if (
            schema.ValueKind == JsonValueKind.Object
            && schema.TryGetProperty("enum", out var enumValues)
            && enumValues.EnumerateArray().Any(value => value.ValueKind == JsonValueKind.Null)
        )
        {
            return true;
        }

        foreach (var unionName in new[] { "anyOf", "oneOf" })
        {
            if (
                schema.ValueKind == JsonValueKind.Object
                && schema.TryGetProperty(unionName, out var alternatives)
                && alternatives.EnumerateArray().Any(AllowsNull)
            )
            {
                return true;
            }
        }

        return false;
    }

    public static IReadOnlySet<string> GetSchemaReferences(JsonElement schema)
    {
        var references = new HashSet<string>(StringComparer.Ordinal);
        CollectSchemaReferences(schema, references);
        return references;
    }

    public static IReadOnlySet<string> GetEnumStrings(JsonElement schema)
    {
        var values = new HashSet<string>(StringComparer.Ordinal);
        CollectEnumStrings(schema, values);
        return values;
    }

    public static IReadOnlyList<JsonElement> GetNonNullAlternatives(JsonElement schema)
    {
        if (
            schema.ValueKind != JsonValueKind.Object
            || !schema.TryGetProperty("anyOf", out var alternatives)
        )
        {
            return [schema];
        }

        return alternatives
            .EnumerateArray()
            .Where(alternative => !IsNullOnly(alternative))
            .ToArray();
    }

    private static JsonDocument LoadDocument()
    {
        var path = Path.Combine(AppContext.BaseDirectory, "openapi.json");
        if (!File.Exists(path))
        {
            throw new FileNotFoundException(
                "The repository-root openapi.json was not copied to the test output directory.",
                path
            );
        }

        return JsonDocument.Parse(File.ReadAllText(path));
    }

    private static bool IsNullOnly(JsonElement schema)
    {
        if (
            schema.ValueKind == JsonValueKind.Object
            && schema.TryGetProperty("type", out var type)
            && type.ValueKind == JsonValueKind.String
            && type.GetString() == "null"
        )
        {
            return true;
        }

        return schema.ValueKind == JsonValueKind.Object
            && schema.TryGetProperty("enum", out var enumValues)
            && enumValues.GetArrayLength() == 1
            && enumValues[0].ValueKind == JsonValueKind.Null;
    }

    private static void CollectSchemaReferences(
        JsonElement element,
        ISet<string> references
    )
    {
        switch (element.ValueKind)
        {
            case JsonValueKind.Object:
                foreach (var property in element.EnumerateObject())
                {
                    if (property.NameEquals("$ref"))
                    {
                        const string prefix = "#/components/schemas/";
                        var reference = property.Value.GetString();
                        if (reference?.StartsWith(prefix, StringComparison.Ordinal) == true)
                        {
                            references.Add(reference[prefix.Length..]);
                        }
                    }
                    else
                    {
                        CollectSchemaReferences(property.Value, references);
                    }
                }

                break;
            case JsonValueKind.Array:
                foreach (var item in element.EnumerateArray())
                {
                    CollectSchemaReferences(item, references);
                }

                break;
        }
    }

    private static void CollectEnumStrings(JsonElement element, ISet<string> values)
    {
        if (element.ValueKind != JsonValueKind.Object)
        {
            return;
        }

        if (element.TryGetProperty("enum", out var enumValues))
        {
            foreach (var value in enumValues.EnumerateArray())
            {
                if (value.ValueKind == JsonValueKind.String)
                {
                    values.Add(value.GetString()!);
                }
            }
        }

        foreach (var unionName in new[] { "anyOf", "oneOf" })
        {
            if (element.TryGetProperty(unionName, out var alternatives))
            {
                foreach (var alternative in alternatives.EnumerateArray())
                {
                    CollectEnumStrings(alternative, values);
                }
            }
        }
    }
}
