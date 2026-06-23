# PasswordLoginParams


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**password** | **str** |  | [optional] 
**username** | **str** |  | [optional] 

## Example

```python
from garm_client.models.password_login_params import PasswordLoginParams

# TODO update the JSON string below
json = "{}"
# create an instance of PasswordLoginParams from a JSON string
password_login_params_instance = PasswordLoginParams.from_json(json)
# print the JSON string representation of the object
print(PasswordLoginParams.to_json())

# convert the object into a dict
password_login_params_dict = password_login_params_instance.to_dict()
# create an instance of PasswordLoginParams from a dict
password_login_params_from_dict = PasswordLoginParams.from_dict(password_login_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


