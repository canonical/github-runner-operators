# CreateGARMToolParams


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**description** | **str** |  | [optional] 
**name** | **str** |  | [optional] 
**origin** | **str** |  | [optional] 
**os_arch** | **str** |  | [optional] 
**os_type** | **str** |  | [optional] 
**size** | **int** |  | [optional] 
**version** | **str** |  | [optional] 

## Example

```python
from garm_client.models.create_garm_tool_params import CreateGARMToolParams

# TODO update the JSON string below
json = "{}"
# create an instance of CreateGARMToolParams from a JSON string
create_garm_tool_params_instance = CreateGARMToolParams.from_json(json)
# print the JSON string representation of the object
print(CreateGARMToolParams.to_json())

# convert the object into a dict
create_garm_tool_params_dict = create_garm_tool_params_instance.to_dict()
# create an instance of CreateGARMToolParams from a dict
create_garm_tool_params_from_dict = CreateGARMToolParams.from_dict(create_garm_tool_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


