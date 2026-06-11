# garm_client.ControllerInfoApi

All URIs are relative to */api/v1*

Method | HTTP request | Description
------------- | ------------- | -------------
[**controller_info**](ControllerInfoApi.md#controller_info) | **GET** /controller-info | Get controller info.


# **controller_info**
> ControllerInfo controller_info()

Get controller info.

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
    api_instance = garm_client.ControllerInfoApi(api_client)

    try:
        # Get controller info.
        api_response = api_instance.controller_info()
        print("The response of ControllerInfoApi->controller_info:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ControllerInfoApi->controller_info: %s\n" % e)
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
**409** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

