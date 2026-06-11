# garm_client.ControllerApi

All URIs are relative to */api/v1*

Method | HTTP request | Description
------------- | ------------- | -------------
[**force_tools_sync**](ControllerApi.md#force_tools_sync) | **POST** /controller/tools/sync | Force immediate sync of GARM agent tools.
[**update_controller**](ControllerApi.md#update_controller) | **PUT** /controller | Update controller.


# **force_tools_sync**
> ControllerInfo force_tools_sync()

Force immediate sync of GARM agent tools.

Forces an immediate sync of GARM agent tools by resetting the cached timestamp.
This will trigger the background worker to fetch the latest tools from the configured
release URL and sync them to the object store.

Note: This endpoint requires that GARM agent tools sync is enabled. If sync is disabled,
the request will return an error.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.controller_info import ControllerInfo
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
    api_instance = garm_client.ControllerApi(api_client)

    try:
        # Force immediate sync of GARM agent tools.
        api_response = api_instance.force_tools_sync()
        print("The response of ControllerApi->force_tools_sync:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ControllerApi->force_tools_sync: %s\n" % e)
```



### Parameters

This endpoint does not need any parameter.

### Return type

[**ControllerInfo**](ControllerInfo.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ControllerInfo |  -  |
**400** | APIErrorResponse |  -  |
**401** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **update_controller**
> ControllerInfo update_controller(body)

Update controller.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.controller_info import ControllerInfo
from garm_client.models.update_controller_params import UpdateControllerParams
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
    api_instance = garm_client.ControllerApi(api_client)
    body = garm_client.UpdateControllerParams() # UpdateControllerParams | Parameters used when updating the controller.

    try:
        # Update controller.
        api_response = api_instance.update_controller(body)
        print("The response of ControllerApi->update_controller:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ControllerApi->update_controller: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **body** | [**UpdateControllerParams**](UpdateControllerParams.md)| Parameters used when updating the controller. | 

### Return type

[**ControllerInfo**](ControllerInfo.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ControllerInfo |  -  |
**400** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

