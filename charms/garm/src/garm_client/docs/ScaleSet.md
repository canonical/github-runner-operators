# ScaleSet


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**created_at** | **datetime** |  | [optional] 
**desired_runner_count** | **int** |  | [optional] 
**disable_update** | **bool** |  | [optional] 
**enable_shell** | **bool** |  | [optional] 
**enabled** | **bool** |  | [optional] 
**endpoint** | [**ForgeEndpoint**](ForgeEndpoint.md) |  | [optional] 
**enterprise_id** | **str** |  | [optional] 
**enterprise_name** | **str** |  | [optional] 
**extended_state** | **str** |  | [optional] 
**extra_specs** | **object** | ExtraSpecs is an opaque raw json that gets sent to the provider as part of the bootstrap params for instances. It can contain any kind of data needed by providers. The contents of this field means nothing to garm itself. We don&#39;t act on the information in this field at all. We only validate that it&#39;s a proper json. | [optional] 
**flavor** | **str** |  | [optional] 
**generation** | **int** | Generation holds the numeric generation of the scaleset. This number will be incremented, every time certain settings of the scaleset, which may influence how runners are created (flavor, specs, image) are changed. When a runner is created, this generation will be copied to the runners as well. That way if some settings diverge, we can target those runners to be recreated. | [optional] 
**github_runner_group** | **str** | GithubRunnerGroup is the github runner group in which the runners will be added. The runner group must be created by someone with access to the enterprise. | [optional] 
**id** | **int** |  | [optional] 
**image** | **str** |  | [optional] 
**instances** | [**List[Instance]**](Instance.md) |  | [optional] 
**max_runners** | **int** |  | [optional] 
**min_idle_runners** | **int** |  | [optional] 
**name** | **str** |  | [optional] 
**org_id** | **str** |  | [optional] 
**org_name** | **str** |  | [optional] 
**os_arch** | **str** |  | [optional] 
**os_type** | **str** |  | [optional] 
**provider_name** | **str** |  | [optional] 
**repo_id** | **str** |  | [optional] 
**repo_name** | **str** |  | [optional] 
**runner_bootstrap_timeout** | **int** |  | [optional] 
**runner_prefix** | **str** |  | [optional] 
**scale_set_id** | **int** |  | [optional] 
**state** | **str** |  | [optional] 
**status_messages** | [**List[StatusMessage]**](StatusMessage.md) |  | [optional] 
**tags** | [**List[Tag]**](Tag.md) |  | [optional] 
**template_id** | **int** |  | [optional] 
**template_name** | **str** |  | [optional] 
**updated_at** | **datetime** |  | [optional] 

## Example

```python
from garm_client.models.scale_set import ScaleSet

# TODO update the JSON string below
json = "{}"
# create an instance of ScaleSet from a JSON string
scale_set_instance = ScaleSet.from_json(json)
# print the JSON string representation of the object
print(ScaleSet.to_json())

# convert the object into a dict
scale_set_dict = scale_set_instance.to_dict()
# create an instance of ScaleSet from a dict
scale_set_from_dict = ScaleSet.from_dict(scale_set_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


