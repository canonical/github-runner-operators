# UpdateTemplateParams


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**data** | **List[int]** |  | [optional] 
**description** | **str** |  | [optional] 
**name** | **str** |  | [optional] 

## Example

```python
from garm_client.models.update_template_params import UpdateTemplateParams

# TODO update the JSON string below
json = "{}"
# create an instance of UpdateTemplateParams from a JSON string
update_template_params_instance = UpdateTemplateParams.from_json(json)
# print the JSON string representation of the object
print(UpdateTemplateParams.to_json())

# convert the object into a dict
update_template_params_dict = update_template_params_instance.to_dict()
# create an instance of UpdateTemplateParams from a dict
update_template_params_from_dict = UpdateTemplateParams.from_dict(update_template_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


