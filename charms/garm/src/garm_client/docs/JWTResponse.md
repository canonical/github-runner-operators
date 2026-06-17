# JWTResponse

JWTResponse holds the JWT token returned as a result of a successful auth

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**token** | **str** |  | [optional] 

## Example

```python
from garm_client.models.jwt_response import JWTResponse

# TODO update the JSON string below
json = "{}"
# create an instance of JWTResponse from a JSON string
jwt_response_instance = JWTResponse.from_json(json)
# print the JSON string representation of the object
print(JWTResponse.to_json())

# convert the object into a dict
jwt_response_dict = jwt_response_instance.to_dict()
# create an instance of JWTResponse from a dict
jwt_response_from_dict = JWTResponse.from_dict(jwt_response_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


