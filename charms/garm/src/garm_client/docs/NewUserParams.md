# NewUserParams

NewUserParams holds the needed information to create a new user

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**email** | **str** |  | [optional] 
**full_name** | **str** |  | [optional] 
**password** | **str** |  | [optional] 
**username** | **str** |  | [optional] 

## Example

```python
from garm_client.models.new_user_params import NewUserParams

# TODO update the JSON string below
json = "{}"
# create an instance of NewUserParams from a JSON string
new_user_params_instance = NewUserParams.from_json(json)
# print the JSON string representation of the object
print(NewUserParams.to_json())

# convert the object into a dict
new_user_params_dict = new_user_params_instance.to_dict()
# create an instance of NewUserParams from a dict
new_user_params_from_dict = NewUserParams.from_dict(new_user_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


