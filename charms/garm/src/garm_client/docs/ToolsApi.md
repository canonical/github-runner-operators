# garm_client.ToolsApi

All URIs are relative to */api/v1*

Method | HTTP request | Description
------------- | ------------- | -------------
[**admin_garm_agent_list**](ToolsApi.md#admin_garm_agent_list) | **GET** /tools/garm-agent | List GARM agent tools for admin users.
[**upload_garm_agent_tool**](ToolsApi.md#upload_garm_agent_tool) | **POST** /tools/garm-agent | Upload a GARM agent tool binary.


# **admin_garm_agent_list**
> GARMAgentToolsPaginatedResponse admin_garm_agent_list(page=page, page_size=page_size, upstream=upstream)

List GARM agent tools for admin users.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.garm_agent_tools_paginated_response import GARMAgentToolsPaginatedResponse
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
    api_instance = garm_client.ToolsApi(api_client)
    page = 56 # int | The page at which to list. (optional)
    page_size = 56 # int | Number of items per page. (optional)
    upstream = True # bool | If true, list tools from the upstream cached release instead of the local object store. (optional)

    try:
        # List GARM agent tools for admin users.
        api_response = api_instance.admin_garm_agent_list(page=page, page_size=page_size, upstream=upstream)
        print("The response of ToolsApi->admin_garm_agent_list:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ToolsApi->admin_garm_agent_list: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **page** | **int**| The page at which to list. | [optional] 
 **page_size** | **int**| Number of items per page. | [optional] 
 **upstream** | **bool**| If true, list tools from the upstream cached release instead of the local object store. | [optional] 

### Return type

[**GARMAgentToolsPaginatedResponse**](GARMAgentToolsPaginatedResponse.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | GARMAgentToolsPaginatedResponse |  -  |
**400** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **upload_garm_agent_tool**
> FileObject upload_garm_agent_tool()

Upload a GARM agent tool binary.

Uploads a GARM agent tool for a specific OS and architecture.
This will automatically replace any existing tool for the same OS/architecture combination.

Uses custom headers for metadata:

X-Tool-Name: Name of the tool

X-Tool-Description: Description

X-Tool-OS-Type: OS type (linux or windows)

X-Tool-OS-Arch: Architecture (amd64 or arm64)

X-Tool-Version: Version string

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
    api_instance = garm_client.ToolsApi(api_client)

    try:
        # Upload a GARM agent tool binary.
        api_response = api_instance.upload_garm_agent_tool()
        print("The response of ToolsApi->upload_garm_agent_tool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ToolsApi->upload_garm_agent_tool: %s\n" % e)
```



### Parameters

This endpoint does not need any parameter.

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
**401** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

