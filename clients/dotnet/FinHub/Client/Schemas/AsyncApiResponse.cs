using System.Text.Json.Serialization;
using MyPo.Shared.Api;

namespace FinHub.Client.Schemas;

public abstract class AsyncApiResponse<TData> : ApiResp<TData>
{
    [JsonPropertyName("extra")]
    public new AsyncTaskInfo Extra
    {
        get => (AsyncTaskInfo)base.Extra!;
        init => base.Extra = value;
    }

    public virtual TResponse ToApiResp<TResponse>() where TResponse : ApiResp<TData>, new()
    {
        return new TResponse
        {
            Status = this.Status,
            Message = this.Message,
            Data = this.Data,
            Extra = this.Extra,
            DebugInfo = this.DebugInfo,
        };
    }
}
