# garm_client.TemplatesApi

All URIs are relative to */api/v1*

Method | HTTP request | Description
------------- | ------------- | -------------
[**create_template**](TemplatesApi.md#create_template) | **POST** /templates | Create template with the parameters given.
[**delete_template**](TemplatesApi.md#delete_template) | **DELETE** /templates/{templateID} | Get template by ID.
[**get_template**](TemplatesApi.md#get_template) | **GET** /templates/{templateID} | Get template by ID.
[**list_templates**](TemplatesApi.md#list_templates) | **GET** /templates | List templates.
[**restore_templates**](TemplatesApi.md#restore_templates) | **POST** /templates/restore | Create template with the parameters given.
[**update_template**](TemplatesApi.md#update_template) | **PUT** /templates/{templateID} | Update template with the parameters given.


# **create_template**
> Template create_template(body)

Create template with the parameters given.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.create_template_params import CreateTemplateParams
from garm_client.models.template import Template
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
    api_instance = garm_client.TemplatesApi(api_client)
    body = garm_client.CreateTemplateParams() # CreateTemplateParams | Parameters used when creating the template.

    try:
        # Create template with the parameters given.
        api_response = api_instance.create_template(body)
        print("The response of TemplatesApi->create_template:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling TemplatesApi->create_template: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **body** | [**CreateTemplateParams**](CreateTemplateParams.md)| Parameters used when creating the template. | 

### Return type

[**Template**](Template.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Template |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **delete_template**
> APIErrorResponse delete_template(template_id)

Get template by ID.

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
    api_instance = garm_client.TemplatesApi(api_client)
    template_id = 3.4 # float | ID of the template to delete.

    try:
        # Get template by ID.
        api_response = api_instance.delete_template(template_id)
        print("The response of TemplatesApi->delete_template:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling TemplatesApi->delete_template: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **template_id** | **float**| ID of the template to delete. | 

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

# **get_template**
> Template get_template(template_id)

Get template by ID.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.template import Template
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
    api_instance = garm_client.TemplatesApi(api_client)
    template_id = 3.4 # float | ID of the template to fetch.

    try:
        # Get template by ID.
        api_response = api_instance.get_template(template_id)
        print("The response of TemplatesApi->get_template:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling TemplatesApi->get_template: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **template_id** | **float**| ID of the template to fetch. | 

### Return type

[**Template**](Template.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Template |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_templates**
> List[Template] list_templates(os_type=os_type, partial_name=partial_name, forge_type=forge_type)

List templates.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.template import Template
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
    api_instance = garm_client.TemplatesApi(api_client)
    os_type = 'os_type_example' # str | OS type of the templates. (optional)
    partial_name = 'partial_name_example' # str | Partial or full name of the template. (optional)
    forge_type = 'forge_type_example' # str | Forge type of the templates. (optional)

    try:
        # List templates.
        api_response = api_instance.list_templates(os_type=os_type, partial_name=partial_name, forge_type=forge_type)
        print("The response of TemplatesApi->list_templates:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling TemplatesApi->list_templates: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **os_type** | **str**| OS type of the templates. | [optional] 
 **partial_name** | **str**| Partial or full name of the template. | [optional] 
 **forge_type** | **str**| Forge type of the templates. | [optional] 

### Return type

[**List[Template]**](Template.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Templates |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **restore_templates**
> APIErrorResponse restore_templates(body)

Create template with the parameters given.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.api_error_response import APIErrorResponse
from garm_client.models.restore_template_request import RestoreTemplateRequest
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
    api_instance = garm_client.TemplatesApi(api_client)
    body = garm_client.RestoreTemplateRequest() # RestoreTemplateRequest | Parameters used when restoring the templates.

    try:
        # Create template with the parameters given.
        api_response = api_instance.restore_templates(body)
        print("The response of TemplatesApi->restore_templates:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling TemplatesApi->restore_templates: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **body** | [**RestoreTemplateRequest**](RestoreTemplateRequest.md)| Parameters used when restoring the templates. | 

### Return type

[**APIErrorResponse**](APIErrorResponse.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **update_template**
> Template update_template(template_id, body)

Update template with the parameters given.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.template import Template
from garm_client.models.update_template_params import UpdateTemplateParams
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
    api_instance = garm_client.TemplatesApi(api_client)
    template_id = 3.4 # float | ID of the template to update.
    body = garm_client.UpdateTemplateParams() # UpdateTemplateParams | Parameters used when updating the template.

    try:
        # Update template with the parameters given.
        api_response = api_instance.update_template(template_id, body)
        print("The response of TemplatesApi->update_template:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling TemplatesApi->update_template: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **template_id** | **float**| ID of the template to update. | 
 **body** | [**UpdateTemplateParams**](UpdateTemplateParams.md)| Parameters used when updating the template. | 

### Return type

[**Template**](Template.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Template |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

