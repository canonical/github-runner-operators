# CreateTemplateParams


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**data** | **str** |  | [optional] 
**description** | **str** |  | [optional] 
**forge_type** | **str** |  | [optional] 
**name** | **str** |  | [optional] 
**os_type** | **str** |  | [optional] 

## Example

```python
from garm_client.models.create_template_params import CreateTemplateParams

# TODO update the JSON string below
json = "{}"
# create an instance of CreateTemplateParams from a JSON string
create_template_params_instance = CreateTemplateParams.from_json(json)
# print the JSON string representation of the object
print(CreateTemplateParams.to_json())

# convert the object into a dict
create_template_params_dict = create_template_params_instance.to_dict()
# create an instance of CreateTemplateParams from a dict
create_template_params_from_dict = CreateTemplateParams.from_dict(create_template_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


