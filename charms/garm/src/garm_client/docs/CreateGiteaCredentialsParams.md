# CreateGiteaCredentialsParams


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**app** | [**GithubApp**](GithubApp.md) |  | [optional] 
**auth_type** | **str** |  | [optional] 
**description** | **str** |  | [optional] 
**endpoint** | **str** |  | [optional] 
**name** | **str** |  | [optional] 
**pat** | [**GithubPAT**](GithubPAT.md) |  | [optional] 

## Example

```python
from garm_client.models.create_gitea_credentials_params import CreateGiteaCredentialsParams

# TODO update the JSON string below
json = "{}"
# create an instance of CreateGiteaCredentialsParams from a JSON string
create_gitea_credentials_params_instance = CreateGiteaCredentialsParams.from_json(json)
# print the JSON string representation of the object
print(CreateGiteaCredentialsParams.to_json())

# convert the object into a dict
create_gitea_credentials_params_dict = create_gitea_credentials_params_instance.to_dict()
# create an instance of CreateGiteaCredentialsParams from a dict
create_gitea_credentials_params_from_dict = CreateGiteaCredentialsParams.from_dict(create_gitea_credentials_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


