# GithubApp


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**app_id** | **int** |  | [optional] 
**installation_id** | **int** |  | [optional] 
**private_key_bytes** | **List[int]** |  | [optional] 

## Example

```python
from garm_client.models.github_app import GithubApp

# TODO update the JSON string below
json = "{}"
# create an instance of GithubApp from a JSON string
github_app_instance = GithubApp.from_json(json)
# print the JSON string representation of the object
print(GithubApp.to_json())

# convert the object into a dict
github_app_dict = github_app_instance.to_dict()
# create an instance of GithubApp from a dict
github_app_from_dict = GithubApp.from_dict(github_app_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


