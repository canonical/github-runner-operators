# UpdateScaleSetParams


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**enable_shell** | **bool** |  | [optional] 
**enabled** | **bool** |  | [optional] 
**extended_state** | **str** |  | [optional] 
**extra_specs** | **object** |  | [optional] 
**flavor** | **str** |  | [optional] 
**image** | **str** |  | [optional] 
**max_runners** | **int** |  | [optional] 
**min_idle_runners** | **int** |  | [optional] 
**name** | **str** |  | [optional] 
**os_arch** | **str** |  | [optional] 
**os_type** | **str** |  | [optional] 
**runner_bootstrap_timeout** | **int** |  | [optional] 
**runner_group** | **str** | GithubRunnerGroup is the github runner group in which the runners of this pool will be added to. The runner group must be created by someone with access to the enterprise. | [optional] 
**runner_prefix** | **str** |  | [optional] 
**state** | **str** |  | [optional] 
**template_id** | **int** |  | [optional] 

## Example

```python
from garm_client.models.update_scale_set_params import UpdateScaleSetParams

# TODO update the JSON string below
json = "{}"
# create an instance of UpdateScaleSetParams from a JSON string
update_scale_set_params_instance = UpdateScaleSetParams.from_json(json)
# print the JSON string representation of the object
print(UpdateScaleSetParams.to_json())

# convert the object into a dict
update_scale_set_params_dict = update_scale_set_params_instance.to_dict()
# create an instance of UpdateScaleSetParams from a dict
update_scale_set_params_from_dict = UpdateScaleSetParams.from_dict(update_scale_set_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


