# HookInfo


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**active** | **bool** |  | [optional] 
**events** | **List[str]** |  | [optional] 
**id** | **int** |  | [optional] 
**insecure_ssl** | **bool** |  | [optional] 
**url** | **str** |  | [optional] 

## Example

```python
from garm_client.models.hook_info import HookInfo

# TODO update the JSON string below
json = "{}"
# create an instance of HookInfo from a JSON string
hook_info_instance = HookInfo.from_json(json)
# print the JSON string representation of the object
print(HookInfo.to_json())

# convert the object into a dict
hook_info_dict = hook_info_instance.to_dict()
# create an instance of HookInfo from a dict
hook_info_from_dict = HookInfo.from_dict(hook_info_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


