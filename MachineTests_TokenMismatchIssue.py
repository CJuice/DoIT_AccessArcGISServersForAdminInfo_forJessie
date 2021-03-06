"""When requesting response from ArcGIS Server about admin services, through a python script, a seemingly random
Client Mismatch error occurs. The error happens when the token being used to access the admin area is not recognized
by the machine being accessed. A web adapter distributes the request to one of four machines. We hypothesized that
a machine was not recognizing tokens generated by one of the other machines. To test this hypothesis we moved the
script to inside the server environment and used server machine names rather than going through the web adapter.
This script runs the tests and was intended to expose the mismatch error and reveal which machine was the issue.
The script gets a token from each machine. Then, for each and every machine, it uses the token and makes requests
to itself and all of the other machines. The request seeks the service reports, which require admin rights.
Unfortunately, we did not see the mismatch error and all machines recognized the tokens from all other machines.
The missing factor appears to be the use of the web adapter though this isn't conclusive proof that the source is with
the web adapter.
20180810, CJuice
"""

def main():
    import configparser
    import json
    import os
    import requests
    import urllib3
    from urllib3.exceptions import InsecureRequestWarning

    # Without disabled warnings, every request prints a red warning since we have chosen 'verify=False' when
    #   making requests to secure services
    urllib3.disable_warnings(InsecureRequestWarning)
    project_root = os.path.dirname(__file__)

    # VARIABLES
    credentials_path = os.path.join(project_root, r"Docs\credentials.cfg")
    config = configparser.ConfigParser()
    config.read(filenames=credentials_path)
    SERVER_PORT_SECURE = config['ags_prod_machine_names']["secureport"]
    SERVER_MACHINE_NAMES = (config['ags_prod_machine_names']["machine1"],
                            config['ags_prod_machine_names']["machine2"],
                            config['ags_prod_machine_names']["machine3"],
                            config['ags_prod_machine_names']["machine4"])
    SERVER_ROOT_URL = "https://{machine_name}:{port}"
    SERVER_URL_GENERATE_TOKEN = "arcgis/admin/generateToken"
    SERVER_URL_SERVICES = "arcgis/admin/services"

    # Need credentials from config file

    username = config['ags_server_credentials']["username"]
    password = config['ags_server_credentials']["password"]

    # CLASSES
    class Machine_Objects():
        """Created to store machine properties and values for use in testing for token recognition issues between machines"""
        def __init__(self, machine_name, root_url, services_url, token, folders):
            self.machine_name = machine_name
            self.root_url = root_url
            self.services_url = services_url
            self.token = token
            self.folders_list = folders
        def __str__(self):
            """Print out a meaningful representation of the object"""
            return(f"{self.machine_name}-->\n\t{self.root_url}\n\t{self.services_url}\n\t{self.token}\n\t{self.folders_list}")

    class Not_JSON_Exception(Exception):
        """Raised when the url for the request is malformed for our purposes and the server returns html, not json"""
        def __init__(self):
            pass

    # FUNCTIONS
    def create_params_for_request(token_action=None):
        if token_action == None:
            values = {'f': 'json'}
        elif token_action == "getToken":
            values = {'username': username, 'password': password, 'client': 'requestip', 'f': 'json'}
        else:
            values = {'token': token_action, 'f': 'json'}
        return values

    def get_value_from_response(serverURL, params, search_key):

        # Handle mixed path slash characters between url syntax and os.path.join use of "\"
        serverURL = clean_url_slashes(serverURL)
        while True:
            try:
                # Jessie discovered "verify" option and set to False to bypass the ssl issue
                response = requests.post(url=serverURL, data=params, verify=False)
            except Exception as e:
                print("Error in response from requests: {}".format(e))
                exit()
            else:
                try:
                    if "html" in response.headers["Content-Type"]:
                        raise Not_JSON_Exception
                    response_json = response.json()
                except json.decoder.JSONDecodeError as jde:
                    print("Error decoding response to json: {}".format(jde))
                    print(response)
                    exit()
                except Not_JSON_Exception as NJE:
                    print("Appears to be html, not json. Problem lies with ...")
                    print(response.url)
                    print(response.headers)
                    print(response.text)
                    exit()

                # In the response json, isolate the value of interest via the search key
                try:
                    value = response_json[search_key]

                # When the search key is not found, throws KeyError. This is where the Client Mismatch error surfaces.
                except KeyError as ke:
                    print("KeyError: {}".format(ke))
                    continue
                except TypeError as te:
                    print("TypeError: {}".format(te))
                    print(response_json)
                    continue
                else:
                    return value

    def clean_url_slashes(url):
        url = url.replace("\\", "/")
        return url

    # FUNCTIONALITY
    # Create combinations of "token generating server" to all other servers for checking tokens to machines acceptance

    machine_objects_list = []
    for machine in SERVER_MACHINE_NAMES:
        root_server_url = SERVER_ROOT_URL.format(machine_name=machine, port=SERVER_PORT_SECURE)

        generate_token_url = os.path.join(root_server_url, SERVER_URL_GENERATE_TOKEN)
        token_params = create_params_for_request(token_action="getToken")
        token = get_value_from_response(serverURL=generate_token_url, params=token_params, search_key="token")

        request_params_result = create_params_for_request(token_action=token)
        services_url = clean_url_slashes(os.path.join(root_server_url, SERVER_URL_SERVICES))
        folders = get_value_from_response(serverURL=services_url, params=request_params_result, search_key="folders")

        #Remove certain folders(System and Utilities per Jessie), and add entry for root folder
        remove_folders = ["System", "Utilities"]
        folders = list(set(folders) - set(remove_folders))
        folders.append("")
        folders.sort()

        # Build machine objects to store the machine names, tokens, urls, etc.
        machine_obj = Machine_Objects(machine_name=machine, root_url=root_server_url, services_url=services_url, token=token, folders=folders)
        machine_objects_list.append(machine_obj)
        print(machine_obj)

    # Step into each machine and get its token
    for outer_machine_object in machine_objects_list:
        print(f"Outer Machine: {outer_machine_object.machine_name}")
        focus_token = outer_machine_object.token

        # Using the token from the outer machine, step into all four machines and make requests for admin services
        #   which require token use. Looking for Client Mismatch issues.
        for inner_machine_object in machine_objects_list:
            print(f"\tInner Machine: {inner_machine_object.machine_name}")
            for folder in inner_machine_object.folders_list:
                if folder != "":
                    folder += "/"
                reportUrl = os.path.join(inner_machine_object.services_url, folder, "report")
                report_request_params = create_params_for_request(token_action=focus_token)

                """In the next step, a return will only occur if the report key is found in the response. If the 
                client mismatch error occurs with the token then the 'reports' key will not be in the response json and
                an KeyError exception will be thrown"""
                reports = get_value_from_response(serverURL=reportUrl, params=report_request_params,
                                                  search_key="reports")
                # print(f"\tReport: {reports}")
            print("\tAll folders accessed")

if __name__ == "__main__":
    main()