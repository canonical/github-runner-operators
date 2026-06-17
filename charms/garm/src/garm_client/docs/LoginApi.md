# garm_client.LoginApi

All URIs are relative to */api/v1*

Method | HTTP request | Description
------------- | ------------- | -------------
[**login**](LoginApi.md#login) | **POST** /auth/login | Logs in a user and returns a JWT token.


# **login**
> JWTResponse login(body)

Logs in a user and returns a JWT token.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.jwt_response import JWTResponse
from garm_client.models.password_login_params import PasswordLoginParams
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
    api_instance = garm_client.LoginApi(api_client)
    body = garm_client.PasswordLoginParams() # PasswordLoginParams | Login information.

    try:
        # Logs in a user and returns a JWT token.
        api_response = api_instance.login(body)
        print("The response of LoginApi->login:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling LoginApi->login: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **body** | [**PasswordLoginParams**](PasswordLoginParams.md)| Login information. | 

### Return type

[**JWTResponse**](JWTResponse.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | JWTResponse |  -  |
**400** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

