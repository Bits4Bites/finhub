from app.schemas import base_req_resp


def test_base_response_omits_unavailable_payload_and_metadata_when_excluding_nulls():
    response = base_req_resp.BaseResponse(status=204, message="No result is available.")

    assert response.model_dump(mode="json", exclude_none=True) == {
        "status": 204,
        "message": "No result is available.",
    }
