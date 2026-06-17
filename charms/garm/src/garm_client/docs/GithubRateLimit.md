# GithubRateLimit


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**limit** | **int** |  | [optional] 
**remaining** | **int** |  | [optional] 
**reset** | **int** |  | [optional] 
**used** | **int** |  | [optional] 

## Example

```python
from garm_client.models.github_rate_limit import GithubRateLimit

# TODO update the JSON string below
json = "{}"
# create an instance of GithubRateLimit from a JSON string
github_rate_limit_instance = GithubRateLimit.from_json(json)
# print the JSON string representation of the object
print(GithubRateLimit.to_json())

# convert the object into a dict
github_rate_limit_dict = github_rate_limit_instance.to_dict()
# create an instance of GithubRateLimit from a dict
github_rate_limit_from_dict = GithubRateLimit.from_dict(github_rate_limit_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


