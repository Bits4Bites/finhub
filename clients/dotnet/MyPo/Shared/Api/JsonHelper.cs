using System.Text.Json;
using System.Text.Json.Serialization;

namespace MyPo.Shared.Api;

public static class JsonHelper
{
	public static T? SafeDeserialize<T>(string v) where T : class
	{
		try
		{
			return JsonSerializer.Deserialize<T>(v, (JsonSerializerOptions?)null);
		}
		catch (JsonException)
		{
			return null;
		}
	}
}
