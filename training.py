import json,csv,sys,os,psycopg2,random
import numpy as np
from collections import Counter 
from processingFunctions import  computeAppStats, countAppOccur, appTimeIntervals, loadStressLabels
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_score, recall_score
import matplotlib.pyplot as plt

day = 86400
halfday = 43200
quarterday = 21600

times =[day,(halfday+quarterday) ,halfday,quarterday]

uids = ['u00','u01','u02','u03','u04','u05','u07','u08','u09','u10','u12','u13','u14','u15','u16','u17','u18','u19','u20','u22','u23','u24',
'u25','u27','u30','u31','u32','u33','u34','u35','u36','u39','u41','u42','u43','u44','u45','u46','u47','u49','u50','u51','u52','u53','u54',
'u56','u57','u58','u59']

uids1=['u10','u16','u19','u33','u44','u36','u57']

ch = [ 25,60,100]



# returns feature vector corresponing to (timestamp,stress_level) (report)
# This feature vector is of size len(uniqueApps), total number of different apps for user
# each cell corresponds to the % of time for one app. Apps that were not used during 
# previous day simply have zero in feature vector cell (sparse)
def appStatsL(cur,uid,timestamp,timeWin,mc):
	appOccurTotal = countAppOccur(cur,uid,mc)
	keys = np.fromiter(iter(appOccurTotal.keys()), dtype=int)
	keys = np.sort(keys)
	appStats1 = np.zeros(len(keys))

	
	tStart = timestamp - timeWin

	cur.execute("""SELECT running_task_id  FROM appusage WHERE uid = %s AND time_stamp > %s AND time_stamp < %s ; """, [uid,tStart,timestamp] )
	records= Counter( cur.fetchall() )
	for k in records.keys():
		records[k[0]] = records.pop(k)


	for i in range(0,len(keys)):
		if keys[i] in records.keys():
			appStats1[i] = float(records[keys[i]])*100 / float(appOccurTotal[keys[i]])

	



	# number of unique applications 
	#uniqueApps = len(records.keys())
	# usageFrequency:  number of times in timeWin / total times
	#usageFrequency= {k: float(records[k])*100/float(appOccurTotal[k]) for k in appOccurTotal.viewkeys() & records.viewkeys() }
	#appStats.append(usageFrequency)
	return appStats1




#---------------------------------------------------------------------
# computes the total time (sec) that screen was on during the past day
def timeScreenOn(cur,uid,timestamp):
	#table name is in form: uXXdark
	uid = uid +'dark'
	#tStart is exactly 24h before given timestamp
	tStart = timestamp - day

	#fetching all records that fall within this time period
	cur.execute('SELECT timeStart,timeStop FROM {0} WHERE timeStart >= {1} AND timeStop <= {2}'.format(uid,tStart,timestamp))
	records = cur.fetchall()

	totalTime =0
	# each tuple contains the time period screen was on. Calculate its duration and add it to total
	for k in records:
		totalTime += k[1]-k[0]

	return totalTime

#-----------------------------------------------------------------------
# computes mean and median of stress reports in order to find the optimal 
# time window for the app statistics calculation to reduce overlapping of features
def meanStress(cur,uid):
	records = sorted( loadStressLabels(cur,uid) , key=lambda x:x[0] )
	mean = 0 

	for i in range(0,len(records)-1):
		mean += records[i][0] - records[i+1][0]

	mean = float(mean) / len(records)
	print(mean)






#testing
con = psycopg2.connect(database='dataset', user='tabrianos')
cur = con.cursor()



# ------------TEST CASE-----------------------------
# 10 user were picked from the dataset
# 70% of their stress reports and the corresponding features are used for training
# the rest 30% is used for testing. The train/test reports are randomly distributed
# throughout the whole experiment duration. No FV is used both for training and testing.
# After the 10 models are trained and tested, the overall accuracy is averaged
# Random Forests were picked due to their 'universal applicability', each with 25 decision trees


# Exhaustive Grid Search Cross-Validation
# training person models with different time period for app usage calculation and different no. of 
# most common apps to figure which outputs the better result 

accuracies = []
for mc in ch:
	for timeWin in times:
		acc=0
		totalP=0
		totalR=0
		for testUser in uids1:

			cur.execute("SELECT time_stamp,stress_level FROM {0}".format(testUser))

			records = cur.fetchall()

			# The intended thing to achieve here is to calculate the feature vector(FV) in the 24h period proceeding each 
			# stress report. Xtrain's rows are those FVs for ALL stress report timestamps 
			a=appStatsL(cur,testUser,records[0][0],timeWin,mc)

			trainLength= int(0.7 * (len(records)))

			#initiating empty numpy arrays to store training and test data/labels
			Xtrain = np.empty([trainLength, len(a)], dtype=float)
			Ytrain = np.empty([trainLength],dtype=int)

			testLength= int(0.3 *len(records))
			Xtest = np.empty([testLength, len(a)], dtype=float)
			Ytest = np.empty(testLength,dtype=int)


			used=[]
			# after this loop, 70% of the data will be in Xtrain (randomly chosen)
			for i in range(0,trainLength):
				trainU = random.choice(records)
				while trainU in used:
					trainU = random.choice(records)
				used.append(trainU)
				Xtrain[i] = appStatsL(cur,testUser,trainU[0],timeWin,mc)
				Ytrain[i] = trainU[1]


			#after this loop, the remaining 30% of data will be in Xtest (randomly chosen)
			for i in range (0,testLength):
				testU = random.choice(records)
				while testU in used:
					testU = random.choice(records)
				used.append(testU)
				Xtest[i] = appStatsL(cur,testUser,testU[0],timeWin,mc)
				Ytest[i] = testU[1]


			#initiating and training forest with 25 trees, n_jobs indicates threads
			forest = RandomForestClassifier(n_estimators=25,n_jobs=4)
			forest = forest.fit(Xtrain,Ytrain)
			
			output = forest.predict(Xtest) 
			
			# because accuracy is never good on its own, precision and recall are computed
			#metricP = precision_score(Ytest,output, average='macro')
			#metricR = recall_score(Ytest,output, average='macro')

			tempAcc = forest.score(Xtest,Ytest)

			#totalP += metricP
			#totalR +=metricR
			acc += tempAcc
			

		print('Average accuracy: {0} %  most common: {1} timewindow: {2}'.format(float(acc)*100/len(uids1), mc,timeWin))
		#print('Average precision: {0} %'.format(float(totalP)*100/len(uids1)))
		#print('Average recall: {0} %'.format(float(totalR)*100/len(uids1)))
		accuracies.append(float(acc)*100/len(uids1))


#x = np.array([i for i in range(0,len(accuracies))])
#y = np.asarray(accuracies)
#xtic = ['One day', '3/4 day','Half day', 'Quarter of day']
#plt.xticks(x, xtic)
#plt.plot(x,y)
#plt.savefig('trainingTimes.png')
