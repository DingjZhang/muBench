import sys
import os
import json
import shutil
# appending a path
sys.path.append('../../')

import K8sYamlBuilder as K8sYamlBuilder
import K8sYamlDeployer as K8sYamlDeployer

import argparse
import argcomplete


### Functions
def create_deployment_config():
    print("---")
    try:
        with open(workmodel_path) as f:
            workmodel = json.load(f)
    except Exception as err:
        print("ERROR: in RunK8sDeployer,", err)
        exit(1)
    K8sYamlBuilder.customization_work_model(workmodel, k8s_parameters)
    K8sYamlBuilder.create_deployment_service_yaml_files(workmodel, k8s_parameters, nfs_conf, builder_module_path)
    K8sYamlBuilder.create_workmodel_configmap_yaml_file(workmodel, k8s_parameters, nfs_conf, builder_module_path)
    K8sYamlBuilder.create_internalservice_configmap_yaml_file(k8s_parameters, nfs_conf, output_path, internal_service_functions_file_path)
    created_items = os.listdir(f"{builder_module_path}/yamls")
    print(f"The following files are created: {created_items}")
    print("---")
    # return a list of the files just created
    return created_items, workmodel

def remove_files(folder_v):
    try:
        folder_items = os.listdir(folder_v)
        print("######################")
        print(f"Removing files in: {folder_v}")
        print("######################")
        for item in folder_items:
            file_path = f"{folder_v}/{item}"
            if os.path.isfile(file_path):
                os.remove(file_path)
                print(f"Removed file: {item}")
        print("---")
    except Exception as er:
        print("######################")
        print(f"Error removing following files: {er}")
        print("######################")


### Main

k8s_Builder_PATH = os.path.dirname(os.path.abspath(__file__))
parser = argparse.ArgumentParser()
parser.add_argument('-c', '--config-file', action='store', dest='parameters_file',
                    help='The K8s Parameters file', default=f'{k8s_Builder_PATH}/K8sParameters.json')
# 添加HPA(Horizontal Pod Autoscaling)命令行选项
parser.add_argument('--hpa', action='store_true', dest='enable_hpa',
                    help='Enable Horizontal Pod Autoscaling', default=False)
parser.add_argument('--hpa-template', type=str, dest='hpa_template_file',
                    help='Path of the HPA YAML file template', default=os.path.abspath(os.path.join(k8s_Builder_PATH, '../../Add-on/HPA/hpa-template.yaml')))


argcomplete.autocomplete(parser)

try:
    args = parser.parse_args()
except ImportError:
    print("Import error, there are missing dependencies to install.  'apt-get install python3-argcomplete "
          "&& activate-global-python-argcomplete3' may solve")
except AttributeError:
    parser.print_help()
except Exception as err:
    print("Error:", err)

#### input params
parameters_file_path = args.parameters_file
# 检查是否启用了HPA
enable_hpa = args.enable_hpa
hpa_template_file = args.hpa_template_file

try:
    with open(parameters_file_path) as f:
        params = json.load(f)
    k8s_parameters = params["K8sParameters"]    
    nfs_conf=dict()
    internal_service_functions_file_path = params['InternalServiceFilePath']
    workmodel_path = params['WorkModelPath']
    no_apply = k8s_parameters['no-apply']

    if "OutputPath" in params.keys() and len(params["OutputPath"]) > 0:
        output_path = params["OutputPath"]
        if output_path.endswith("/"):
            output_path = output_path[:-1]
        if not os.path.exists(output_path):
            os.makedirs(output_path)
    else:
        output_path = None

except Exception as err:
    print("ERROR: in RunK8sDeployer,", err)
    exit(1)


###  Create YAML, insert files (workmodel.json and custom function) as configmaps, and deploy YAML 

folder_not_exist = False
if output_path is None:
    builder_module_path = K8sYamlBuilder.K8s_YAML_BUILDER_PATH
else:
    builder_module_path = output_path
if not os.path.exists(f"{builder_module_path}/yamls"):
    folder_not_exist = True
folder = f"{builder_module_path}/yamls"
hpa_yamls_folder = f"{builder_module_path}/hpa_yamls"

if folder_not_exist or len(os.listdir(folder)) == 0:

    # keyboard_input = input("\nDirectory empty, wanna DEPLOY? (y)").lower() or "y"
    keyboard_input = "y"

    if keyboard_input == "y" or keyboard_input == "yes":
        # Create YAML files
        updated_folder_items, work_model = create_deployment_config()   

        if not no_apply:
            K8sYamlDeployer.deploy_items(folder, st=k8s_parameters['sleep'])
            if enable_hpa:
                K8sYamlBuilder.add_hpa_to_yaml_files(folder, hpa_template_file, hpa_yamls_folder)
                K8sYamlDeployer.deploy_items(hpa_yamls_folder, st=k8s_parameters['sleep'])
    else:
        print("...\nOk you do not want to DEPLOY stuff! Bye!")
else:
    print("######################")
    print("!!!! Warning !!!!")
    print("######################")
    print(f"Folder is not empty: {folder}.")
    keyboard_input = input("Do you want to UNDEPLOY yamls of the old application first, delete the files and then start the new applicaiton ? (n) ") or "n"
    if keyboard_input == "y" or keyboard_input == "yes":
        if not enable_hpa:
            if not no_apply:
                K8sYamlDeployer.undeploy_items(folder)
            remove_files(folder)
        # if hpa_yamls_folder exists:
        else:
            if not no_apply:
                K8sYamlDeployer.undeploy_items(folder)
                K8sYamlDeployer.undeploy_items(hpa_yamls_folder)
            # if os.path.exists(hpa_yamls_folder):
            remove_files(hpa_yamls_folder)
            remove_files(folder)
    else:
        print("...\nOk you want to keep the OLD application! Bye!")

