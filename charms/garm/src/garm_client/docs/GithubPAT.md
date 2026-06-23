# GithubPAT


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**oauth2_token** | **str** |  | [optional] 

## Example

```python
from garm_client.models.github_pat import GithubPAT

# TODO update the JSON string below
json = "{}"
# create an instance of GithubPAT from a JSON string
github_pat_instance = GithubPAT.from_json(json)
# print the JSON string representation of the object
print(GithubPAT.to_json())

# convert the object into a dict
github_pat_dict = github_pat_instance.to_dict()
# create an instance of GithubPAT from a dict
github_pat_from_dict = GithubPAT.from_dict(github_pat_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


