import json
import time
import argparse
import argcomplete
import os

def workloadGen(trace, output_dir, output_file=None, ingress_service='s0', multiplier=1):
    """
    根据trace生成workload文件
    """
    # 读取trace文件
    if not output_file:
        output_file = 'workload.json'
    if not os.path.exists(output_dir):
        print(f'make dir: {output_dir}')
        os.makedirs(output_dir)
    qps_data = []
    with open(trace, 'r') as f:
        lines = f.readlines()
        for l in lines:
            qps_data.append(float(l.strip()))
    
    start_time = 0
    events = list()
    events_time_lst = list()
    qps_data = qps_data[:300]
    for index, qps in enumerate(qps_data):
        qps = qps * multiplier
        interval = 1000.0 / qps if qps > 0 else 1000
        for i in range(int(qps)):
            events_time = int(start_time + i * interval)
            if events_time in events_time_lst:
                continue
            events.append({
                "time": events_time,
                "service": ingress_service})
        start_time = index * 1000 + 1000
    print(f"Output dir: {os.path.join(output_dir, output_file)}")
    with open(os.path.join(output_dir, output_file), 'w') as f:
        json.dump(events, f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--trace', type=str, help='trace file path', 
                        dest='trace', action='store')
    parser.add_argument('-o', '--output_dir', type=str, help='output dir path', 
                        dest='output_dir', action='store')
    parser.add_argument('-f', '--output_file', type=str, help='output file name', 
                        dest='output_file', action='store', default='workload.json')
    parser.add_argument('-i', '--ingress_service', type=str, help='ingress service name',
                        dest='ingress_service', action='store', default='s0')
    parser.add_argument('-m', '--multiplier', type=int, help='multiplier',
                        dest='multiplier', action='store', default=1)
    argcomplete.autocomplete(parser)
    args = parser.parse_args()
    workloadGen(args.trace, args.output_dir, args.output_file, args.ingress_service, args.multiplier)


if __name__ == '__main__':
    main()
