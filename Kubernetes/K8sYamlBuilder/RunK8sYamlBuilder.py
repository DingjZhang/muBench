from K8sYamlBuilder import customization_work_model, create_deployment_yaml_files, K8s_YAML_BUILDER_PATH
import json
from pprint import pprint
import sys
import os
import shutil

if len(sys.argv) > 1:
    parameters_file_path = sys.argv[1]
else:
    parameters_file_path = f'{K8s_YAML_BUILDER_PATH}/K8sParameters.json'

try:
    with open(parameters_file_path) as f:
        params = json.load(f)

    k8s_parameters = params["K8sParameters"]
    work_model_path = params['WorkModelPath']
    nfs_conf = params['NFSConfigurations']
    if "OutputPath" in params.keys() and len(params["OutputPath"]) > 0:
        output_path = params["OutputPath"]
        if output_path.endswith("/"):
            output_path = output_path[:-1]
        if not os.path.exists(output_path):
            os.makedirs(output_path)
        out_work_model_path = f"{output_path}/{work_model_path.split('/')[-1]}"
    else:
        out_work_model_path = work_model_path
        output_path = K8s_YAML_BUILDER_PATH
except Exception as err:
    print("ERROR: in RunK8sYamlBuilder,", err)
    exit(1)

with open(work_model_path, "r") as f:
    work_model = json.load(f)

customization_work_model(work_model, k8s_parameters)

pprint(work_model)

with open(out_work_model_path, "w") as f:
    f.write(json.dumps(work_model, indent=2))

if output_path != K8s_YAML_BUILDER_PATH:
    shutil.copy(parameters_file_path, f"{output_path}/")

create_deployment_yaml_files(work_model, k8s_parameters, nfs_conf, output_path)
