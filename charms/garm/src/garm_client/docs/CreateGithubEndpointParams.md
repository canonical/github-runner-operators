# CreateGithubEndpointParams


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**api_base_url** | **str** |  | [optional] 
**base_url** | **str** |  | [optional] 
**ca_cert_bundle** | **bytes** |  | [optional] 
**description** | **str** |  | [optional] 
**name** | **str** |  | [optional] 
**upload_base_url** | **str** |  | [optional] 

## Example

```python
from garm_client.models.create_github_endpoint_params import CreateGithubEndpointParams

# TODO update the JSON string below
json = "{}"
# create an instance of CreateGithubEndpointParams from a JSON string
create_github_endpoint_params_instance = CreateGithubEndpointParams.from_json(json)
# print the JSON string representation of the object
print(CreateGithubEndpointParams.to_json())

# convert the object into a dict
create_github_endpoint_params_dict = create_github_endpoint_params_instance.to_dict()
# create an instance of CreateGithubEndpointParams from a dict
create_github_endpoint_params_from_dict = CreateGithubEndpointParams.from_dict(create_github_endpoint_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


