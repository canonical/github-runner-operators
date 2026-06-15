# APIErrorResponse


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**details** | **str** |  | [optional] 
**error** | **str** |  | [optional] 

## Example

```python
from garm_client.models.api_error_response import APIErrorResponse

# TODO update the JSON string below
json = "{}"
# create an instance of APIErrorResponse from a JSON string
api_error_response_instance = APIErrorResponse.from_json(json)
# print the JSON string representation of the object
print(APIErrorResponse.to_json())

# convert the object into a dict
api_error_response_dict = api_error_response_instance.to_dict()
# create an instance of APIErrorResponse from a dict
api_error_response_from_dict = APIErrorResponse.from_dict(api_error_response_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


