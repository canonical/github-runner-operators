# UpdateGithubEndpointParams


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**api_base_url** | **str** |  | [optional] 
**base_url** | **str** |  | [optional] 
**ca_cert_bundle** | **List[int]** |  | [optional] 
**description** | **str** |  | [optional] 
**upload_base_url** | **str** |  | [optional] 

## Example

```python
from garm_client.models.update_github_endpoint_params import UpdateGithubEndpointParams

# TODO update the JSON string below
json = "{}"
# create an instance of UpdateGithubEndpointParams from a JSON string
update_github_endpoint_params_instance = UpdateGithubEndpointParams.from_json(json)
# print the JSON string representation of the object
print(UpdateGithubEndpointParams.to_json())

# convert the object into a dict
update_github_endpoint_params_dict = update_github_endpoint_params_instance.to_dict()
# create an instance of UpdateGithubEndpointParams from a dict
update_github_endpoint_params_from_dict = UpdateGithubEndpointParams.from_dict(update_github_endpoint_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


