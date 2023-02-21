import os
import pandas as pd


def adjust_csv(database_path: str):
    if not os.path.exists(database_path):
        raise Exception('audio路径不存在')
    df = pd.read_csv(database_path, encoding="utf-8-sig", header=None)
    for i in range(0, len(df)):
        if df.iloc[i - 1, 4] == '全员':
            df.iloc[i - 1, 4] = 'EOE'
    df.to_csv(database_path, index=False, header=None)


def adjust_two_files_name():
    def adjust_file_name(directory: str):
        for filename in os.listdir(directory):
            if os.path.isfile(os.path.join(directory, filename)):
                split = filename.split(" ")
                if len(split) > 1 and '合唱' in split[1]:
                    split[1] = 'EOE'
                new_filename = ' '.join(split)
                os.rename(os.path.join(directory, filename), os.path.join(directory, new_filename))
    adjust_file_name('./audio')
    adjust_file_name('./cover')
