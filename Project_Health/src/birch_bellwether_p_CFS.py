import pandas as pd
import numpy as np
import math
import pickle

from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn import metrics
from sklearn.naive_bayes import GaussianNB
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import StratifiedKFold
from sklearn.model_selection import KFold

import platform
from os import listdir
from os.path import isfile, join
from glob import glob
from pathlib import Path
import sys
import os
import copy
import traceback
import timeit
import random


import matplotlib.pyplot as plt

import birch
from predictor_advance_v1 import *
import utils
import CFS_regression as CFS


from multiprocessing import Pool, cpu_count
from threading import Thread
from multiprocessing import Queue

# import metrices

import sys
import traceback
import warnings
warnings.filterwarnings("ignore")

class ThreadWithReturnValue(Thread):
    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs={}, Verbose=None):
        Thread.__init__(self, group, target, name, args, kwargs)
        self._return = None
    def run(self):
        #print(type(self._target))
        if self._target is not None:
            self._return = self._target(*self._args,
                                                **self._kwargs)
    def join(self, *args):
        Thread.join(self, *args)
        return self._return



class Bellwether(object):

    def __init__(self,data_path,attr_df, goal, month):
        self.directory = data_path
        self.attr_df = attr_df
        self.cores = 8
        self.goal = goal
        self.metrics = 0
        self.month = month

            
    def prepare_data(self, repo_name):
        df_raw = pd.read_csv(self.directory + repo_name, sep=',')
        df_raw = df_raw.drop(columns=['dates'])  
        last_col = utils.get_goal(self.goal)
        cols = list(df_raw.columns.values)
        cols.sort()
        cols.remove(last_col)
        df_adjust = df_raw[cols+[last_col]]
        return df_adjust

    def apply_cfs(self, df):
        goal = utils.get_goal(self.goal)
        y = df[goal].values
        X_df = df.drop(labels = [goal],axis = 1)
        X = X_df.values
        selected_cols = CFS.cfs(X,y)
        cols = X_df.columns[[selected_cols]].tolist()
        cols.append(goal)
        return df[cols],cols


    # Cluster Driver
    def cluster_driver(self,df,print_tree = True):
        X = df.apply(pd.to_numeric)
        cluster = birch.birch(branching_factor=20)
        cluster.fit(X)
        cluster_tree,max_depth = cluster.get_cluster_tree()
        if print_tree:
            cluster.show_clutser_tree()
        return cluster,cluster_tree,max_depth

    def build_BIRCH(self):
        goal_name = utils.get_goal(self.goal)
        # self.attr_df = self.attr_df.drop(goal_name, axis = 1)
        # print(goal_name,self.attr_df.columns)
        cluster,cluster_tree,max_depth = self.cluster_driver(self.attr_df)
        return cluster,cluster_tree,max_depth

    
    def bellwether(self,selected_projects,all_projects):
        final_score = {}
        final_model = {}
        final_features = {}
        count = 0
        for s_project in selected_projects:
            try:
                data = self.prepare_data(s_project)
                data, cols = self.apply_cfs(data)
                list_temp, model_touse = DECART_bellwether_CFS(data, self.metrics, 
                                            self.month, all_projects, s_project, 
                                            self.directory, self.goal, cols)
                final_score[s_project] = list_temp
                final_model[s_project] = model_touse
                final_features[s_project] = cols
            except ArithmeticError as e:
                print(e)
                continue
        return [final_score, final_model, final_features]

    def run_bellwether(self,projects):
        threads = []
        results = {}
        models = {}
        features = {}
        _projects = projects
        split_projects = np.array_split(_projects, self.cores)
        for i in range(self.cores):
            print("starting thread ",i)
            t = ThreadWithReturnValue(target = self.bellwether, args = [split_projects[i],projects])
            threads.append(t)
        for th in threads:
            th.start()
        for th in threads:
            response = th.join()
            results.update(response[0])
            models.update(response[1])
            features.update(response[2])
        return results, models, features

    def run(self,selected_projects,cluster_id,data_store_path):
        print(cluster_id)
        final_score, models, features = self.run_bellwether(selected_projects)
        data_path = Path(data_store_path + utils.get_goal(self.goal) + '/' + str(cluster_id))
        if not data_path.is_dir():
            os.makedirs(data_path)
        with open(data_store_path + utils.get_goal(self.goal) + '/' + str(cluster_id) + '/goal_' + str(self.goal)  + '.pkl', 'wb') as handle:
            pickle.dump(final_score, handle, protocol=pickle.HIGHEST_PROTOCOL)
        
        with open(data_store_path + utils.get_goal(self.goal) + '/' + str(cluster_id) + '/goal_' + str(self.goal)  + '_models.pkl', 'wb') as handle:
            pickle.dump(models, handle, protocol=pickle.HIGHEST_PROTOCOL)

        with open(data_store_path + utils.get_goal(self.goal) + '/' + str(cluster_id) + '/goal_' + str(self.goal)  + '_features.pkl', 'wb') as handle:
            pickle.dump(features, handle, protocol=pickle.HIGHEST_PROTOCOL)
        # df = pd.read_pickle(data_store_path + str(cluster_id)  + '/700_RF_default_bellwether.pkl')


if __name__ == "__main__":
    month = 6
    for i in range(7):
        print('Running Goal:', i)
        goal = utils.get_goal(i)
        start = timeit.default_timer()
        path = 'data/data_use/'
        meta_path = 'results/attribute/data_attribute_' + goal + '.csv'
        data_store_path = 'results/with_CFS_DE/month_' + str(month) + '_models/'
        attr_df = pd.read_csv(meta_path, index_col=0)

        attr_df_index = list(attr_df.index)
        training_projects = random.sample(attr_df_index, 1200)
        test_projects = []
        for project in attr_df_index:
            if project not in training_projects:
                test_projects.append(project)

        attr_df_train = attr_df.loc[training_projects]
        attr_df_test = attr_df.loc[test_projects]

        bell = Bellwether(path,attr_df_train,i,month)
        cluster,cluster_tree,max_depth = bell.build_BIRCH()

        cluster_ids = []
        for key in cluster_tree:
            if cluster_tree[key].depth == max_depth:
                cluster_ids.append(key)

        for ids in cluster_ids:
            selected_projects = list(attr_df_train.loc[cluster_tree[ids].data_points].index)
            print(selected_projects)
            bell.run(selected_projects,ids,data_store_path)

        data_path = Path(data_store_path + goal)
        if not data_path.is_dir():
            os.makedirs(data_path)

        attr_df_train.to_pickle(data_store_path + '/' + goal + '/train_data.pkl')
        attr_df_test.to_pickle(data_store_path + '/' + goal + '/test_data.pkl')

        stop = timeit.default_timer() 
        print("Model training time: ", stop - start)
