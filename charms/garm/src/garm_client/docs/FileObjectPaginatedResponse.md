# FileObjectPaginatedResponse


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**current_page** | **int** |  | [optional] 
**next_page** | **int** |  | [optional] 
**pages** | **int** |  | [optional] 
**previous_page** | **int** |  | [optional] 
**results** | [**List[FileObjectPaginatedResponseResultsInner]**](FileObjectPaginatedResponseResultsInner.md) |  | [optional] 
**total_count** | **int** |  | [optional] 

## Example

```python
from garm_client.models.file_object_paginated_response import FileObjectPaginatedResponse

# TODO update the JSON string below
json = "{}"
# create an instance of FileObjectPaginatedResponse from a JSON string
file_object_paginated_response_instance = FileObjectPaginatedResponse.from_json(json)
# print the JSON string representation of the object
print(FileObjectPaginatedResponse.to_json())

# convert the object into a dict
file_object_paginated_response_dict = file_object_paginated_response_instance.to_dict()
# create an instance of FileObjectPaginatedResponse from a dict
file_object_paginated_response_from_dict = FileObjectPaginatedResponse.from_dict(file_object_paginated_response_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


