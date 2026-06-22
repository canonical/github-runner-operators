# CreateFileObjectParams


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**description** | **str** |  | [optional] 
**name** | **str** |  | [optional] 
**size** | **int** |  | [optional] 
**tags** | **List[str]** |  | [optional] 

## Example

```python
from garm_client.models.create_file_object_params import CreateFileObjectParams

# TODO update the JSON string below
json = "{}"
# create an instance of CreateFileObjectParams from a JSON string
create_file_object_params_instance = CreateFileObjectParams.from_json(json)
# print the JSON string representation of the object
print(CreateFileObjectParams.to_json())

# convert the object into a dict
create_file_object_params_dict = create_file_object_params_instance.to_dict()
# create an instance of CreateFileObjectParams from a dict
create_file_object_params_from_dict = CreateFileObjectParams.from_dict(create_file_object_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


