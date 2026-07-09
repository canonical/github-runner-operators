# ForgeCredentials


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**api_base_url** | **str** |  | [optional] 
**auth_type** | **str** |  | [optional] 
**base_url** | **str** |  | [optional] 
**ca_bundle** | **bytes** |  | [optional] 
**created_at** | **datetime** |  | [optional] 
**description** | **str** |  | [optional] 
**endpoint** | [**ForgeEndpoint**](ForgeEndpoint.md) |  | [optional] 
**enterprises** | [**List[Enterprise]**](Enterprise.md) |  | [optional] 
**forge_type** | **str** |  | [optional] 
**id** | **int** |  | [optional] 
**name** | **str** |  | [optional] 
**organizations** | [**List[Organization]**](Organization.md) |  | [optional] 
**rate_limit** | [**GithubRateLimit**](GithubRateLimit.md) |  | [optional] 
**repositories** | [**List[Repository]**](Repository.md) |  | [optional] 
**updated_at** | **datetime** |  | [optional] 
**upload_base_url** | **str** |  | [optional] 

## Example

```python
from garm_client.models.forge_credentials import ForgeCredentials

# TODO update the JSON string below
json = "{}"
# create an instance of ForgeCredentials from a JSON string
forge_credentials_instance = ForgeCredentials.from_json(json)
# print the JSON string representation of the object
print(ForgeCredentials.to_json())

# convert the object into a dict
forge_credentials_dict = forge_credentials_instance.to_dict()
# create an instance of ForgeCredentials from a dict
forge_credentials_from_dict = ForgeCredentials.from_dict(forge_credentials_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


