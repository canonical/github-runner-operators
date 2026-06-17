# MetadataServiceAccessDetails


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**agent_url** | **str** |  | [optional] 
**callback_url** | **str** |  | [optional] 
**metadata_url** | **str** |  | [optional] 

## Example

```python
from garm_client.models.metadata_service_access_details import MetadataServiceAccessDetails

# TODO update the JSON string below
json = "{}"
# create an instance of MetadataServiceAccessDetails from a JSON string
metadata_service_access_details_instance = MetadataServiceAccessDetails.from_json(json)
# print the JSON string representation of the object
print(MetadataServiceAccessDetails.to_json())

# convert the object into a dict
metadata_service_access_details_dict = metadata_service_access_details_instance.to_dict()
# create an instance of MetadataServiceAccessDetails from a dict
metadata_service_access_details_from_dict = MetadataServiceAccessDetails.from_dict(metadata_service_access_details_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


