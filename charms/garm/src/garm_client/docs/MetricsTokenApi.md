# garm_client.MetricsTokenApi

All URIs are relative to */api/v1*

Method | HTTP request | Description
------------- | ------------- | -------------
[**get_metrics_token**](MetricsTokenApi.md#get_metrics_token) | **GET** /metrics-token | Returns a JWT token that can be used to access the metrics endpoint.


# **get_metrics_token**
> JWTResponse get_metrics_token()

Returns a JWT token that can be used to access the metrics endpoint.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.jwt_response import JWTResponse
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
    api_instance = garm_client.MetricsTokenApi(api_client)

    try:
        # Returns a JWT token that can be used to access the metrics endpoint.
        api_response = api_instance.get_metrics_token()
        print("The response of MetricsTokenApi->get_metrics_token:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling MetricsTokenApi->get_metrics_token: %s\n" % e)
```



### Parameters

This endpoint does not need any parameter.

### Return type

[**JWTResponse**](JWTResponse.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | JWTResponse |  -  |
**401** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

