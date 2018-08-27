"""
Uses a single ArcGIS Server machine to interrogate the status of services and outputs a json file of the results.

Randomly accessing one of the four ags machines by machine name to bypass the web adaptor. This is done to avoid a
Client Mismatch Erros related to token recognition failures by machines when run using geodata.md.gov (web adaptor).
A request is made to a machine first for a token and then for information on services on the machine. The information
is used to write an output json file that is later used by the status dashboard web page to display performance for
the services.

Name:        AGS Directory to list of started/not with stats
Purpose:     Use for status dashboard within DoIT
Author: JCahoon
Revised: 20180702, JCahoon, Modifications to work with Python 3 library
Revised: 20180821, CJuice, Redesigned to be object oriented, and addressed Client Mismatch Error issue related to
    token recognition failures by arcgis server machines. Accessing machines directly, bypassing the web adaptor,
    and suppressing Insecure Request Warnings.
Revised:
"""


def main():

    import configparser
    import json
    import os
    import random
    import requests
    # urllib3 is included in requests but to manage the InsecureRequestWarning it was also imported directly
    import urllib3
    from urllib3.exceptions import InsecureRequestWarning

    # Without disabled warnings, every request would print a red warning. This is because we have chosen
    #   'verify=False' when making requests to secure services.
    urllib3.disable_warnings(InsecureRequestWarning)

    # VARIABLES
    _ROOT_PROJECT_PATH = os.path.dirname(__file__)
    CREDENTIALS_PATH = os.path.join(_ROOT_PROJECT_PATH, "Docs/credentials.cfg")
    config = configparser.ConfigParser()    # Need sensitive information from config file
    config.read(filenames=CREDENTIALS_PATH)

    GEODATA_ALIAS = "Geodata Data"
    GROUPED_TYPES_LIST = ("GeometryServer", "SearchServer", "GlobeServer", "GPServer", "GeocodeServer", "GeoDataServer")
    PASSWORD = config['ags_server_credentials']["password"]
    RESULT_FILE = "GeodataServices.json"
    SERVER_MACHINE_NAMES = {0: config['ags_prod_machine_names']["machine1"],
                            1: config['ags_prod_machine_names']["machine2"],
                            2: config['ags_prod_machine_names']["machine3"],
                            3: config['ags_prod_machine_names']["machine4"]}
    SERVER_PORT_SECURE = config['ags_prod_machine_names']["secureport"]
    SERVER_ROOT_URL = "https://{machine_name}.mdgov.maryland.gov:{port}"
    SERVER_URL_ADMIN_SERVICES = "arcgis/admin/services"
    SERVER_URL_GENERATE_TOKEN = "arcgis/admin/generateToken"
    USERNAME = config['ags_server_credentials']["username"]

    # CLASSES
    class ReportObject:
        """Reports are summaries of services within folders."""
        GEODATA_ROOT = "https://geodata.md.gov/imap/rest/services"
        REST_URL_BEGINNING = "https://{machine_name}.mdgov.maryland.gov:{port}/arcgis/rest/services"
        REST_URL_END = "{folder}/{service_name}/{type}"

        def __init__(self, report, folder, machine_name):
            """
            Instantiate an ReportObject
            :param report: json object with information about the services
            :param folder: the folder in the services directory
            :param machine_name: the name of the ags server machine currently being interrogated for information
            """
            self.folder = folder
            self.type = report["type"]
            self.service_name = report["serviceName"]
            self.rest_service_url_machine = machine_name
            self.rest_service_url_geodata = None
            self.real_time_status = report["status"]["realTimeState"]
            self.cached = "NA"
            self.feature_service = "NA"
            self.kml = "NA"
            self.wms = "NA"
            self.wfs = "NA"
            self.layers = "NA"
            self.extensions = report["extensions"]

        def create_base_dictionary(self):
            """
            Creates a dictionary of attributes for json.dumps() consumption.
            This base dictionary is common to all service types.
            :return:
            """
            data = {"ServiceName": self.service_name,
                    "Server": GEODATA_ALIAS,
                    "Folder": self.folder,
                    "URL": self.rest_service_url_geodata,
                    "Type": self.type,
                    "Status": self.real_time_status,
                    "Cached": self.cached,
                    "FeatureService": self.feature_service,
                    "kml": self.kml,
                    "wms": self.wms,
                    "wfs": self.wfs}
            return data

        @property
        def folder(self):
            return self.__folder

        @folder.setter
        def folder(self, value):
            self.__folder = value.replace("/", "")

        @property
        def rest_service_url_geodata(self):
            return self.__rest_service_url_geodata

        @rest_service_url_geodata.setter
        def rest_service_url_geodata(self, value):
            """
            Creates the url for a service with geodata.md.gov rather than the machine name
            :param value: Not used, no initial assignment value
            :return: None
            """
            ending = ReportObject.REST_URL_END.format(folder=self.folder, service_name=self.service_name, type=self.type)
            self.__rest_service_url_geodata = f"{ReportObject.GEODATA_ROOT}/{ending}"

        @property
        def rest_service_url_machine(self):
            return self.__rest_service_url_machine

        @rest_service_url_machine.setter
        def rest_service_url_machine(self, value):
            """
            Creates the url for a service with the machine name for use from a web server to bypass the web adaptor
            :param value: Initial assignment value is the machine name only
            :return: None
            """
            beginning = ReportObject.REST_URL_BEGINNING.format(machine_name=value, port=SERVER_PORT_SECURE)
            ending = ReportObject.REST_URL_END.format(folder=self.folder, service_name=self.service_name, type=self.type)
            self.__rest_service_url_machine = f"{beginning}/{ending}"

        def create_json_string(self, data, indent=4):
            """
            Create and return a json string from a dictionary.
            Intended to accept the base dictionary.
            :param data: a dictionary; designed to accept the base dictionary
            :param indent: json output pretty indent dimension (default=4)
            :return: json
            """
            return json.dumps(obj=data, indent=indent)

        def create_json_string_mapserver(self, data, indent=4):
            """
            Add a key/value pair to a dictionary and then create and return a json string from that dictionary.
            Intended to accept the base dictionary and then add a key/value specific to MapServer type services.
            :param data: a dictionary; designed to accept the base dictionary
            :param indent: json output pretty indent dimension (default=4)
            :return: json
            """
            data["layers"] = self.layers
            return json.dumps(obj=data, indent=indent)

    class MachineObject:
        """Created to store machine properties and values."""
        def __init__(self, machine_name, root_url, admin_services_url, token, folders):
            """
            Instantiate the machine objects
            :param machine_name: name of the server machine
            :param root_url: root url for machine
            :param admin_services_url: root url for machine plus /arcgis/admin/services
            :param token: the token generated by the machine for secure access
            :param folders: list of folders discovered during inspection of the services
            """
            self.machine_name = machine_name
            self.root_url = root_url
            self.admin_services_url = admin_services_url
            self.token = token
            self.folders_list = folders
        def __str__(self):
            """
            Overriding the __str__ builtin to control the appearance of the machine object print-out for readability.
            :return: string
            """
            return f"{self.machine_name}-->\n\t{self.root_url}\n\t{self.admin_services_url}\n\t{self.token}\n\t{self.folders_list}"

    class NotJSONException(Exception):
        """Raised when the url for the request is malformed for our purposes and the server returns html, not json"""
        def __init__(self):
            pass

    # FUNCTIONS
    def create_params_for_request(token_action=None):
        """
        Create parameters to be submitted with the request.
        :param token_action: route to be taken when creating the parameters
        :return: dictionary of parameters
        """
        if token_action == None:
            values = {'f': 'json'}
        elif token_action == "getToken":
            values = {'username': USERNAME, 'password': PASSWORD, 'client': 'requestip', 'f': 'json'}
        else:
            values = {'token': token_action, 'f': 'json'}
        return values

    def get_value_from_response(url, params, search_key):
        """
        Submit a request with parameters to a url and inspect the response json for the specified key of interest.
        :param url: url to which to make a request
        :param params: parameters to accompany the request
        :param search_key: the key of interest in the response json
        :return: content of json if key present in response
        """
        # To deal with mixed path characters between url syntax and os.path.join use of "\"
        url = clean_url_slashes(url)

        # FROM ORIGINAL DESIGN HANDLING CLIENT MISMATCH ERROR CONCERNING TOKEN RECOGNITION
        # To deal with the client mismatch error we were encountering, we used the following 'While' to make repeated
        #   requests as a bypass. If the error is no longer encountered because the machine name is now used to bypass
        #   the web adapter, which seemed to be connected to the issue with token mismatches, then the process will run
        #   the first time so the 'While' is removed but may be of value if similar errors arise in the future.
        # while True:

        try:
            # Jessie discovered "verify" option and set to False to bypass the ssl issue
            response = requests.post(url=url, data=params, verify=False)
        except Exception as e:
            print("Error in response from requests: {}".format(e))
            exit()
        else:
            try:
                if "html" in response.headers["Content-Type"]:
                    raise NotJSONException
                response_json = response.json()
            except json.decoder.JSONDecodeError as jde:
                print("Error decoding response to json: {}".format(jde))
                print(response)
                exit()
            except NotJSONException as NJE:
                print("Appears to be html, not json. Problem lies with ...")
                print(response.url)
                print(response.headers)
                print(response.text)
                exit()
            try:
                value = response_json[search_key]
            except KeyError as ke:
                print("KeyError: {}".format(ke))
                # continue      # for While loop usage
                exit()
            except TypeError as te:
                print("TypeError: {}".format(te))
                print(response_json)
                # continue       # for While loop usage
                exit()
            else:
                return value

    def clean_url_slashes(url):
        """
        Standardize the slashes when use of os.path.join() with forward slashes in url's.
        os.path.join() uses back slashes '\' while http uses forward slashes '/'
        :param url: url to be examined
        :return: standardized url string
        """
        url = url.replace("\\", "/")
        return url

    def create_random_int(upper_integer):
        """
        Create and return a random integer from 0 to one less than the upper range value.
        :param upper_integer: upper integer of range to be used
        :return: integer
        """
        options = upper_integer - 1
        spot = random.randint(0, options)
        return spot

    def extract_extension_properties(extensions_dict, name_check, extensions="extensions", type_name="typeName"):
        """
        Create and return a list of extensions values for a service based on the service type
        :param extensions_dict: extensions dictionary to be inspected
        :param name_check: name to check the type against
        :param extensions: default use was 'extensions' per Jessie's design but could be other values too
        :param type_name: default use was 'typeName' per Jessie's design but could be other values too
        :return: list
        """
        return [entity for entity in extensions_dict[extensions] if entity[type_name] == name_check]

    # FUNCTIONALITY
    #   Select a machine at random to which to make a request.
    machine = SERVER_MACHINE_NAMES[create_random_int(upper_integer=len(SERVER_MACHINE_NAMES))]
    print(f"MACHINE: {machine}")

    #   Get a token
    root_server_url = SERVER_ROOT_URL.format(machine_name=machine, port=SERVER_PORT_SECURE)
    generate_token_url = os.path.join(root_server_url, SERVER_URL_GENERATE_TOKEN)
    token_params = create_params_for_request(token_action="getToken")
    token = get_value_from_response(url=generate_token_url, params=token_params, search_key="token")

    #   Make a request for secure services using the token
    request_params_result = create_params_for_request(token_action=token)
    admin_services_full_url = clean_url_slashes(os.path.join(root_server_url, SERVER_URL_ADMIN_SERVICES))
    folders = get_value_from_response(url=admin_services_full_url,
                                      params=request_params_result,
                                      search_key="folders")

    #   Remove certain folders (System and Utilities per Jessie), and append entry for root folder
    remove_folders = ["System", "Utilities"]
    folders = list(set(folders) - set(remove_folders))
    folders.append("")
    folders.sort()

    #   Create a machine object for the selected ArcGIS Server machine.
    machine_object = MachineObject(machine_name=machine,
                                    root_url=root_server_url,
                                    admin_services_url=admin_services_full_url,
                                    token=token,
                                    folders=folders)

    #   Initiate the output file
    machine_result_file = f"{RESULT_FILE}"
    service_results_file_handler = open(os.path.join(_ROOT_PROJECT_PATH, machine_result_file), 'w')
    service_results_file_handler.write("[")

    #   Loop on the found folders, discover the services, and write the services information
    folder_iteration_count = 0
    for folder in machine_object.folders_list:
        print(f"\nFOLDER: {folder} - {folder_iteration_count + 1} of {len(machine_object.folders_list)}")

        # Determine if the current iteration is examining the root folder. If is, do nothing
        folder_iteration_count += 1
        if folder == "" or folder == "/":   # Unclear why Jessie included 'folder == "/"' but am preserving
            continue
        else:

            # Build the URL for the current folder
            folder += "/"
            report_url = os.path.join(machine_object.admin_services_url, folder, "report")
            report_request_params = create_params_for_request(token_action=machine_object.token)
            reports = get_value_from_response(url=report_url, params=report_request_params, search_key="reports")

            # Inspect service reports
            report_iteration_count = 0
            for report in reports:
                line = ""
                if folder == "":
                    folder_name = "Root"
                else:
                    folder_name = folder

                report_object = ReportObject(report=report, folder=folder_name, machine_name=machine)
                if report_object.type in GROUPED_TYPES_LIST:
                    line = report_object.create_json_string(data=report_object.create_base_dictionary())
                elif report_object.type == "MapServer":

                    # Check for Map Cache
                    report_object.cached = report["properties"]["isCached"]

                    if len(report_object.extensions) > 0:

                        # Extract the KML, WMS, WFS, and FeatureServer properties from the response
                        # Current design makes a list containing one dictionary. It then accesses the dictionary by
                        #   specifying the zero index of the list to get the dict and then requests the 'enabled' key.
                        #   TODO: Improvement - redesign for use of report object and simplify
                        kml_properties = extract_extension_properties(extensions_dict=report, name_check="KmlServer")
                        wms_properties = extract_extension_properties(extensions_dict=report, name_check="WMSServer")
                        wfs_properties = extract_extension_properties(extensions_dict=report, name_check="WFSServer")
                        feature_server_properties = extract_extension_properties(extensions_dict=report,
                                                                                 name_check="FeatureServer")
                        if len(feature_server_properties) > 0:
                            report_object.feature_service = str(feature_server_properties[0]["enabled"])
                        if len(kml_properties) > 0:
                            report_object.kml = str(kml_properties[0]["enabled"])
                        if len(wms_properties) > 0:
                            report_object.wms = str(wms_properties[0]["enabled"])
                        if len(wfs_properties) > 0:
                            report_object.wfs = str(wfs_properties[0]["enabled"])

                    # Handle map server layers. Functionality unique to Map Server.
                    layer_iteration_count = 0
                    layers_string = "["
                    if report_object.real_time_status == "STARTED":
                        layer_request_params = create_params_for_request()
                        layers = get_value_from_response(url=report_object.rest_service_url_machine,
                                                         params=layer_request_params,
                                                         search_key="layers")
                        try:
                            for layer in layers:
                                if layer_iteration_count == 0:
                                    pass
                                else:
                                    layers_string += ","
                                layer_data_dict = {"id": str(layer["id"]), "name": layer["name"]}
                                layers_string += json.dumps(layer_data_dict)
                                layer_iteration_count += 1
                        except Exception as e:
                            print(f'No layers. {e}')
                    layers_string += "]"
                    report_object.layers = layers_string
                    line = report_object.create_json_string_mapserver(data=report_object.create_base_dictionary())
                elif report["type"] == "ImageServer":
                    wms_properties = extract_extension_properties(extensions_dict=report, name_check="WMSServer")
                    if len(wms_properties) > 0:
                        report_object.wms = str(wms_properties[0]["enabled"])
                    line = report_object.create_json_string(data=report_object.create_base_dictionary())
                else:
                    # line would still be == "" if this else is accessed
                    pass

                # Insert a comma before all lines except for the first service report or where the line is empty.
                if report_iteration_count == 0 or line == "":
                    pass
                else:
                    line = f",{line}"

                # Write the results to the file, unless the line is empty
                if line == "":
                    pass
                else:
                    service_results_file_handler.write(line)
                    report_iteration_count += 1

            # Insert a comma after all of a folders services have been processed
            #   ***Except after the last folder of the entire output.
            if folder_iteration_count < (len(folders)) and report_iteration_count > 0:
                comma = ","
                service_results_file_handler.write(comma)
            else:
                pass

    service_results_file_handler.write("]")
    service_results_file_handler.close()


if __name__ == "__main__":
    main()
