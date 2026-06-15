# garm_client.ObjectsApi

All URIs are relative to */api/v1*

Method | HTTP request | Description
------------- | ------------- | -------------
[**delete_file_object**](ObjectsApi.md#delete_file_object) | **DELETE** /objects/{objectID} | Delete a file object.
[**get_file_object**](ObjectsApi.md#get_file_object) | **GET** /objects/{objectID} | Get a file object.
[**list_file_objects**](ObjectsApi.md#list_file_objects) | **GET** /objects | List file objects.
[**update_file_object**](ObjectsApi.md#update_file_object) | **PUT** /objects/{objectID} | Update a file object.


# **delete_file_object**
> APIErrorResponse delete_file_object(object_id)

Delete a file object.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.api_error_response import APIErrorResponse
from garm_client.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to /api/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = garm_client.Configuration(
    host = "/api/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: Bearer
configuration.api_key['Bearer'] = os.environ["API_KEY"]

# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Bearer'] = 'Bearer'

# Enter a context with an instance of the API client
with garm_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = garm_client.ObjectsApi(api_client)
    object_id = 'object_id_example' # str | The ID of the file object.

    try:
        # Delete a file object.
        api_response = api_instance.delete_file_object(object_id)
        print("The response of ObjectsApi->delete_file_object:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ObjectsApi->delete_file_object: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **object_id** | **str**| The ID of the file object. | 

### Return type

[**APIErrorResponse**](APIErrorResponse.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **get_file_object**
> FileObject get_file_object(object_id)

Get a file object.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.file_object import FileObject
from garm_client.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to /api/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = garm_client.Configuration(
    host = "/api/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: Bearer
configuration.api_key['Bearer'] = os.environ["API_KEY"]

# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Bearer'] = 'Bearer'

# Enter a context with an instance of the API client
with garm_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = garm_client.ObjectsApi(api_client)
    object_id = 'object_id_example' # str | The ID of the file object.

    try:
        # Get a file object.
        api_response = api_instance.get_file_object(object_id)
        print("The response of ObjectsApi->get_file_object:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ObjectsApi->get_file_object: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **object_id** | **str**| The ID of the file object. | 

### Return type

[**FileObject**](FileObject.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | FileObject |  -  |
**400** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_file_objects**
> FileObjectPaginatedResponse list_file_objects(tags=tags, page=page, page_size=page_size)

List file objects.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.file_object_paginated_response import FileObjectPaginatedResponse
from garm_client.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to /api/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = garm_client.Configuration(
    host = "/api/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: Bearer
configuration.api_key['Bearer'] = os.environ["API_KEY"]

# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Bearer'] = 'Bearer'

# Enter a context with an instance of the API client
with garm_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = garm_client.ObjectsApi(api_client)
    tags = 'tags_example' # str | List of tags to filter by. (optional)
    page = 56 # int | The page at which to list. (optional)
    page_size = 56 # int | Number of items per page. (optional)

    try:
        # List file objects.
        api_response = api_instance.list_file_objects(tags=tags, page=page, page_size=page_size)
        print("The response of ObjectsApi->list_file_objects:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ObjectsApi->list_file_objects: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **tags** | **str**| List of tags to filter by. | [optional] 
 **page** | **int**| The page at which to list. | [optional] 
 **page_size** | **int**| Number of items per page. | [optional] 

### Return type

[**FileObjectPaginatedResponse**](FileObjectPaginatedResponse.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | FileObjectPaginatedResponse |  -  |
**400** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **update_file_object**
> FileObject update_file_object(object_id, body)

Update a file object.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.file_object import FileObject
from garm_client.models.update_file_object_params import UpdateFileObjectParams
from garm_client.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to /api/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = garm_client.Configuration(
    host = "/api/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: Bearer
configuration.api_key['Bearer'] = os.environ["API_KEY"]

# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Bearer'] = 'Bearer'

# Enter a context with an instance of the API client
with garm_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = garm_client.ObjectsApi(api_client)
    object_id = 'object_id_example' # str | The ID of the file object.
    body = garm_client.UpdateFileObjectParams() # UpdateFileObjectParams | Parameters used when updating a file object.

    try:
        # Update a file object.
        api_response = api_instance.update_file_object(object_id, body)
        print("The response of ObjectsApi->update_file_object:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ObjectsApi->update_file_object: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **object_id** | **str**| The ID of the file object. | 
 **body** | [**UpdateFileObjectParams**](UpdateFileObjectParams.md)| Parameters used when updating a file object. | 

### Return type

[**FileObject**](FileObject.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | FileObject |  -  |
**400** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

