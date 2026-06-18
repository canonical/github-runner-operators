# UpdateGiteaCredentialsParams


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**description** | **str** |  | [optional] 
**name** | **str** |  | [optional] 
**pat** | [**GithubPAT**](GithubPAT.md) |  | [optional] 

## Example

```python
from garm_client.models.update_gitea_credentials_params import UpdateGiteaCredentialsParams

# TODO update the JSON string below
json = "{}"
# create an instance of UpdateGiteaCredentialsParams from a JSON string
update_gitea_credentials_params_instance = UpdateGiteaCredentialsParams.from_json(json)
# print the JSON string representation of the object
print(UpdateGiteaCredentialsParams.to_json())

# convert the object into a dict
update_gitea_credentials_params_dict = update_gitea_credentials_params_instance.to_dict()
# create an instance of UpdateGiteaCredentialsParams from a dict
update_gitea_credentials_params_from_dict = UpdateGiteaCredentialsParams.from_dict(update_gitea_credentials_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


