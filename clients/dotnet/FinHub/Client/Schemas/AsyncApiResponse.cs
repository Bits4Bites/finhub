using System.Text.Json.Serialization;
using MyPo.Shared.Api;

namespace FinHub.Client.Schemas;

public abstract class AsyncApiResponse<TData> : ApiResp<TData>
{
    [JsonPropertyName("extra")]
    public new required AsyncTaskInfo Extra
    {
        get => (AsyncTaskInfo)base.Extra!;
        init => base.Extra = value;
    }
}
