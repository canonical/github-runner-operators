# garm_client.FirstRunApi

All URIs are relative to */api/v1*

Method | HTTP request | Description
------------- | ------------- | -------------
[**first_run**](FirstRunApi.md#first_run) | **POST** /first-run | Initialize the first run of the controller.


# **first_run**
> User first_run(body)

Initialize the first run of the controller.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.new_user_params import NewUserParams
from garm_client.models.user import User
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
    api_instance = garm_client.FirstRunApi(api_client)
    body = garm_client.NewUserParams() # NewUserParams | Create a new user.

    try:
        # Initialize the first run of the controller.
        api_response = api_instance.first_run(body)
        print("The response of FirstRunApi->first_run:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling FirstRunApi->first_run: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **body** | [**NewUserParams**](NewUserParams.md)| Create a new user. | 

### Return type

[**User**](User.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | User |  -  |
**400** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

