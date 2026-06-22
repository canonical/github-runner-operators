# garm_client.CredentialsApi

All URIs are relative to */api/v1*

Method | HTTP request | Description
------------- | ------------- | -------------
[**create_credentials**](CredentialsApi.md#create_credentials) | **POST** /github/credentials | Create a GitHub credential.
[**create_gitea_credentials**](CredentialsApi.md#create_gitea_credentials) | **POST** /gitea/credentials | Create a Gitea credential.
[**delete_credentials**](CredentialsApi.md#delete_credentials) | **DELETE** /github/credentials/{id} | Delete a GitHub credential.
[**delete_gitea_credentials**](CredentialsApi.md#delete_gitea_credentials) | **DELETE** /gitea/credentials/{id} | Delete a Gitea credential.
[**get_credentials**](CredentialsApi.md#get_credentials) | **GET** /github/credentials/{id} | Get a GitHub credential.
[**get_gitea_credentials**](CredentialsApi.md#get_gitea_credentials) | **GET** /gitea/credentials/{id} | Get a Gitea credential.
[**list_credentials**](CredentialsApi.md#list_credentials) | **GET** /github/credentials | List all credentials.
[**list_gitea_credentials**](CredentialsApi.md#list_gitea_credentials) | **GET** /gitea/credentials | List all credentials.
[**update_credentials**](CredentialsApi.md#update_credentials) | **PUT** /github/credentials/{id} | Update a GitHub credential.
[**update_gitea_credentials**](CredentialsApi.md#update_gitea_credentials) | **PUT** /gitea/credentials/{id} | Update a Gitea credential.


# **create_credentials**
> ForgeCredentials create_credentials(body)

Create a GitHub credential.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.create_github_credentials_params import CreateGithubCredentialsParams
from garm_client.models.forge_credentials import ForgeCredentials
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
    api_instance = garm_client.CredentialsApi(api_client)
    body = garm_client.CreateGithubCredentialsParams() # CreateGithubCredentialsParams | Parameters used when creating a GitHub credential.

    try:
        # Create a GitHub credential.
        api_response = api_instance.create_credentials(body)
        print("The response of CredentialsApi->create_credentials:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling CredentialsApi->create_credentials: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **body** | [**CreateGithubCredentialsParams**](CreateGithubCredentialsParams.md)| Parameters used when creating a GitHub credential. | 

### Return type

[**ForgeCredentials**](ForgeCredentials.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ForgeCredentials |  -  |
**400** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **create_gitea_credentials**
> ForgeCredentials create_gitea_credentials(body)

Create a Gitea credential.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.create_gitea_credentials_params import CreateGiteaCredentialsParams
from garm_client.models.forge_credentials import ForgeCredentials
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
    api_instance = garm_client.CredentialsApi(api_client)
    body = garm_client.CreateGiteaCredentialsParams() # CreateGiteaCredentialsParams | Parameters used when creating a Gitea credential.

    try:
        # Create a Gitea credential.
        api_response = api_instance.create_gitea_credentials(body)
        print("The response of CredentialsApi->create_gitea_credentials:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling CredentialsApi->create_gitea_credentials: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **body** | [**CreateGiteaCredentialsParams**](CreateGiteaCredentialsParams.md)| Parameters used when creating a Gitea credential. | 

### Return type

[**ForgeCredentials**](ForgeCredentials.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ForgeCredentials |  -  |
**400** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **delete_credentials**
> APIErrorResponse delete_credentials(id)

Delete a GitHub credential.

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
    api_instance = garm_client.CredentialsApi(api_client)
    id = 56 # int | ID of the GitHub credential.

    try:
        # Delete a GitHub credential.
        api_response = api_instance.delete_credentials(id)
        print("The response of CredentialsApi->delete_credentials:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling CredentialsApi->delete_credentials: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **id** | **int**| ID of the GitHub credential. | 

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

# **delete_gitea_credentials**
> APIErrorResponse delete_gitea_credentials(id)

Delete a Gitea credential.

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
    api_instance = garm_client.CredentialsApi(api_client)
    id = 56 # int | ID of the Gitea credential.

    try:
        # Delete a Gitea credential.
        api_response = api_instance.delete_gitea_credentials(id)
        print("The response of CredentialsApi->delete_gitea_credentials:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling CredentialsApi->delete_gitea_credentials: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **id** | **int**| ID of the Gitea credential. | 

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

# **get_credentials**
> ForgeCredentials get_credentials(id)

Get a GitHub credential.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.forge_credentials import ForgeCredentials
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
    api_instance = garm_client.CredentialsApi(api_client)
    id = 56 # int | ID of the GitHub credential.

    try:
        # Get a GitHub credential.
        api_response = api_instance.get_credentials(id)
        print("The response of CredentialsApi->get_credentials:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling CredentialsApi->get_credentials: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **id** | **int**| ID of the GitHub credential. | 

### Return type

[**ForgeCredentials**](ForgeCredentials.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ForgeCredentials |  -  |
**400** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **get_gitea_credentials**
> ForgeCredentials get_gitea_credentials(id)

Get a Gitea credential.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.forge_credentials import ForgeCredentials
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
    api_instance = garm_client.CredentialsApi(api_client)
    id = 56 # int | ID of the Gitea credential.

    try:
        # Get a Gitea credential.
        api_response = api_instance.get_gitea_credentials(id)
        print("The response of CredentialsApi->get_gitea_credentials:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling CredentialsApi->get_gitea_credentials: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **id** | **int**| ID of the Gitea credential. | 

### Return type

[**ForgeCredentials**](ForgeCredentials.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ForgeCredentials |  -  |
**400** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_credentials**
> List[ForgeCredentials] list_credentials()

List all credentials.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.forge_credentials import ForgeCredentials
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
    api_instance = garm_client.CredentialsApi(api_client)

    try:
        # List all credentials.
        api_response = api_instance.list_credentials()
        print("The response of CredentialsApi->list_credentials:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling CredentialsApi->list_credentials: %s\n" % e)
```



### Parameters

This endpoint does not need any parameter.

### Return type

[**List[ForgeCredentials]**](ForgeCredentials.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Credentials |  -  |
**400** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_gitea_credentials**
> List[ForgeCredentials] list_gitea_credentials()

List all credentials.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.forge_credentials import ForgeCredentials
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
    api_instance = garm_client.CredentialsApi(api_client)

    try:
        # List all credentials.
        api_response = api_instance.list_gitea_credentials()
        print("The response of CredentialsApi->list_gitea_credentials:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling CredentialsApi->list_gitea_credentials: %s\n" % e)
```



### Parameters

This endpoint does not need any parameter.

### Return type

[**List[ForgeCredentials]**](ForgeCredentials.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Credentials |  -  |
**400** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **update_credentials**
> ForgeCredentials update_credentials(id, body)

Update a GitHub credential.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.forge_credentials import ForgeCredentials
from garm_client.models.update_github_credentials_params import UpdateGithubCredentialsParams
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
    api_instance = garm_client.CredentialsApi(api_client)
    id = 56 # int | ID of the GitHub credential.
    body = garm_client.UpdateGithubCredentialsParams() # UpdateGithubCredentialsParams | Parameters used when updating a GitHub credential.

    try:
        # Update a GitHub credential.
        api_response = api_instance.update_credentials(id, body)
        print("The response of CredentialsApi->update_credentials:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling CredentialsApi->update_credentials: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **id** | **int**| ID of the GitHub credential. | 
 **body** | [**UpdateGithubCredentialsParams**](UpdateGithubCredentialsParams.md)| Parameters used when updating a GitHub credential. | 

### Return type

[**ForgeCredentials**](ForgeCredentials.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ForgeCredentials |  -  |
**400** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **update_gitea_credentials**
> ForgeCredentials update_gitea_credentials(id, body)

Update a Gitea credential.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.forge_credentials import ForgeCredentials
from garm_client.models.update_gitea_credentials_params import UpdateGiteaCredentialsParams
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
    api_instance = garm_client.CredentialsApi(api_client)
    id = 56 # int | ID of the Gitea credential.
    body = garm_client.UpdateGiteaCredentialsParams() # UpdateGiteaCredentialsParams | Parameters used when updating a Gitea credential.

    try:
        # Update a Gitea credential.
        api_response = api_instance.update_gitea_credentials(id, body)
        print("The response of CredentialsApi->update_gitea_credentials:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling CredentialsApi->update_gitea_credentials: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **id** | **int**| ID of the Gitea credential. | 
 **body** | [**UpdateGiteaCredentialsParams**](UpdateGiteaCredentialsParams.md)| Parameters used when updating a Gitea credential. | 

### Return type

[**ForgeCredentials**](ForgeCredentials.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ForgeCredentials |  -  |
**400** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

