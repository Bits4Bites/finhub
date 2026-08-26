using System.Text.Json;
using System.Text.Json.Serialization;

namespace MyPo.Shared.Api;

/// <summary>
/// Response to an API call.
/// </summary>
public class ApiResp
{
	/// <summary>
	/// Status of the API call, following HTTP status codes convention.
	/// </summary>
	[JsonPropertyName("status")]
	public int Status { get; set; }

	[JsonIgnore]
	public bool IsSuccess => Status >= 200 && Status < 300;

	/// <summary>
	/// Extra information if any (e.g. the detailed error message).
	/// </summary>
	[JsonPropertyName("message"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
	public string? Message { get; set; }

	/// <summary>
	/// Extra data if any.
	/// </summary>
	[JsonPropertyName("extra"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
	public virtual object? Extra { get; set; }

    public virtual T? ExtraAs<T>() where T : class
    {
        return JsonHelper.SafeDeserialize<T>(JsonSerializer.Serialize(Extra, (JsonSerializerOptions?)null));
    }

	/// <summary>
	/// Debug information if any.
	/// </summary>
	[JsonPropertyName("debug_info"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
	public virtual object? DebugInfo { get; set; }

	public virtual T? DebugInfoAs<T>() where T : class
    {
        return JsonHelper.SafeDeserialize<T>(JsonSerializer.Serialize(DebugInfo, (JsonSerializerOptions?)null));
    }
}

/// <summary>
/// Typed version of <see cref="ApiResp"/>.
/// </summary>
/// <typeparam name="T"></typeparam>
public class ApiResp<T> : ApiResp
{
	/// <summary>
	/// The data returned by the API call (specific to individual API).
	/// </summary>
	[JsonPropertyName("data"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
	public virtual T? Data { get; set; }
}
