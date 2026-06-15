# UpdateFileObjectParams


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**description** | **str** |  | [optional] 
**name** | **str** |  | [optional] 
**tags** | **List[str]** |  | [optional] 

## Example

```python
from garm_client.models.update_file_object_params import UpdateFileObjectParams

# TODO update the JSON string below
json = "{}"
# create an instance of UpdateFileObjectParams from a JSON string
update_file_object_params_instance = UpdateFileObjectParams.from_json(json)
# print the JSON string representation of the object
print(UpdateFileObjectParams.to_json())

# convert the object into a dict
update_file_object_params_dict = update_file_object_params_instance.to_dict()
# create an instance of UpdateFileObjectParams from a dict
update_file_object_params_from_dict = UpdateFileObjectParams.from_dict(update_file_object_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


