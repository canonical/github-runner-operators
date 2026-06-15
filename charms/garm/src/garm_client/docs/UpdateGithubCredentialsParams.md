# UpdateGithubCredentialsParams


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**app** | [**GithubApp**](GithubApp.md) |  | [optional] 
**description** | **str** |  | [optional] 
**name** | **str** |  | [optional] 
**pat** | [**GithubPAT**](GithubPAT.md) |  | [optional] 

## Example

```python
from garm_client.models.update_github_credentials_params import UpdateGithubCredentialsParams

# TODO update the JSON string below
json = "{}"
# create an instance of UpdateGithubCredentialsParams from a JSON string
update_github_credentials_params_instance = UpdateGithubCredentialsParams.from_json(json)
# print the JSON string representation of the object
print(UpdateGithubCredentialsParams.to_json())

# convert the object into a dict
update_github_credentials_params_dict = update_github_credentials_params_instance.to_dict()
# create an instance of UpdateGithubCredentialsParams from a dict
update_github_credentials_params_from_dict = UpdateGithubCredentialsParams.from_dict(update_github_credentials_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


