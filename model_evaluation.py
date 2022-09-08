import os, glob, cv2, sys, re, time, csv
import numpy as np
import tensorflow as tf
import matplotlib.pyplot as plt
import sklearn
from sklearn.metrics import PrecisionRecallDisplay
from sklearn.metrics import precision_recall_curve
from sklearn.metrics import average_precision_score
from typing import Union
from my_feature_extractor import FeatureExtractor
from my_eval_tool import Eval_tool

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

FOLDER_PATH = "C:\kwoncy\eye\image_datas\\6_sixth_make_roi_with_bad_video_images\\test_with_clean_imgs"
# FOLDER_PATH = "C:\kwoncy\eye\image_datas\\6_sixth_make_roi_with_bad_video_images\\test_with_little_bad_imgs"
# FOLDER_PATH = "C:\kwoncy\eye\image_datas\\6_sixth_make_roi_with_bad_video_images\\test_with_bad_imgs"
CURRENT_DEVICE = "/device:CPU:0"
MODEL_NAME = "new2_pupil3_320x240_6912_E30_B5_R4444_S9709.h5"

def dice_score(y_true:np.ndarray, y_pred:np.ndarray) -> float:
    # y_true_f = y_true.reshape(-1,1)
    y_true_f = y_true
    # y_pred_f = y_pred.reshape(-1,1)
    y_pred_f = y_pred

    intersection = np.sum(y_true_f * y_pred_f)
    return (2. * intersection) / (np.sum(y_true_f) + np.sum(y_pred_f) + 1e-7)


## this function evaluate model with whole image's differencies [0,1]
def model_evaluate_with_predicted_images2(folder_path:str)->dict:
    ## make predicted images
    if not check_folder_predicted_images(folder_path):
        make_predicted_images_to_folder(folder_path)
        
    ## check if predicted images made
    if not check_folder_predicted_images(folder_path):
        raise Exception("from model_evaluate_with_predicted_images(): coudn't make predicted image or wrong number or images")
    
    indices, pred_npimgs, mask_npimgs = load_pred_gray_and_mask_gray_imgs(folder_path)
    print(mask_npimgs.shape)
    
    pred_npimgs_binary = pred_npimgs / 255.
    mask_npimgs_binary = mask_npimgs / 255.


    tn, fp, fn, tp  = sklearn.metrics.confusion_matrix(mask_npimgs_binary.flatten(),pred_npimgs_binary.flatten()).ravel()
    print(" tn: ",tn," fp: ",fp," fn: ",fn," tp: ",tp)
    sensitivity = tp/(tp+fn)
    print("Sensitivity: ", sensitivity)
    specificity = tn/(tn+fp)
    print("Specificity: ", specificity)
    precision = tp/(tp+fp)
    print("Precision: ", precision)
    accuracy = (tp+tn)/(tp+tn+fp+fn)
    print("Accuracy: ", accuracy)
    f1_score = 2*sensitivity*precision/(sensitivity+precision)
    print("F1-score: ", f1_score)


## this function evaluate model with not whole image's differencies [0,1], only IOU area
def model_evaluate_with_predicted_images(folder_path:str)->dict:
    ## make predicted images
    if not check_folder_predicted_images(folder_path):
        make_predicted_images_to_folder(folder_path)
        
    ## check if predicted images made
    if not check_folder_predicted_images(folder_path):
        raise Exception("from model_evaluate_with_predicted_images(): coudn't make predicted image or wrong number or images")
    
    indices, pred_npimgs, mask_npimgs = load_pred_gray_and_mask_gray_imgs(folder_path)
    print(mask_npimgs.shape)
    mask_pixels = np.sum(mask_npimgs, axis=(1,2))
    pred_pixels = np.sum(pred_npimgs, axis=(1,2))
    
    # undetecteds = np.where(mask_pixels==0)[0]
    # print(undetecteds)

    confusion_matrix = get_confusion_matrix_dict(pred_npimgs, mask_npimgs)
    print(confusion_matrix)

    y_true, y_pred = get_pseudo_y_with_cm(TP=confusion_matrix["TP"], FP=confusion_matrix["FP"], TN=confusion_matrix["TN"], FN=confusion_matrix["FN"])

    AP_score = get_average_precision_score(y_true, y_pred, flag_draw=True)
    print(AP_score)

## the folder must have like below condition.
## index_orig.png , index_mask.png
def check_folder_predicted_images(folder_path:str) -> bool:
    orig_file_list = glob.glob(f'{folder_path}/*_orig.png')
    mask_file_list = glob.glob(f'{folder_path}/*_mask.png')
    pred_file_list = glob.glob(f'{folder_path}/*_predicted.png')
    if len(pred_file_list) != len(mask_file_list) or len(mask_file_list) != len(orig_file_list):
        print("len_orig_file: ",len(orig_file_list))
        print("len_mask_file: ",len(mask_file_list))
        print("len_pred_file: ",len(pred_file_list))
        return False
    return True

def make_predicted_images_to_folder(folder_path:str):
    orig_file_list = glob.glob(f'{folder_path}/*_orig.png')
    re_orig = re.compile('([0-9]+)_orig.png')
    pred_file_list = []    
    orig_imgs = []
    for orig_file in orig_file_list:
        head, tail = os.path.split(orig_file)
        num_str = re_orig.match(tail).group(1)
        pred_file_list.append(os.path.join(head, num_str + "_predicted.png"))
        
        orig_imgs.append(cv2.imread(orig_file,cv2.IMREAD_GRAYSCALE))
        

    orig_npimgs = np.stack(orig_imgs).astype(np.float32)
    orig_npimgs /= 255.
    with tf.device(CURRENT_DEVICE):
        model = tf.keras.models.load_model(MODEL_NAME, custom_objects={'dice_score':dice_score})
        start_time = time.time()
        preds = model.predict(orig_npimgs[:,:,:,np.newaxis])
        preds = preds.squeeze()
        preds = (preds > 0.5).astype(np.uint8)
        preds = preds * 255
        print(f"({preds.shape[0]}) predict time: ",time.time()-start_time)
        
        for idx, image in enumerate(preds):
            cv2.imwrite(pred_file_list[idx], image)


def load_pred_gray_and_mask_gray_imgs(folder_path:str)->'list[np.ndarray, np.ndarray, np.ndarray]':
    mask_file_list = glob.glob(f'{folder_path}/*_mask.png')
    re_mask = re.compile('([0-9]+)_mask.png')
    mask_imgs = []
    pred_imgs = []
    indices = []

    for mask_file in mask_file_list:
        head, tail = os.path.split(mask_file)
        num_str = re_mask.match(tail).group(1)
        indices.append(int(num_str))
        pred_file = os.path.join(head, num_str + "_predicted.png")

        mask_imgs.append(cv2.imread(mask_file,cv2.IMREAD_GRAYSCALE))
        pred_imgs.append(cv2.imread(pred_file,cv2.IMREAD_GRAYSCALE))

    return [np.array(indices), np.array(pred_imgs), np.array(mask_imgs)]


def get_mask_and_pred_centers_with_index(folder_path:str, roundness:int=None)->'list[list[int], list[Union[float,None]], list[Union[float,None]], list[Union[float,None]], list[Union[float,None]]]':
    eval_tool = Eval_tool()
    fe = FeatureExtractor()
    indices, pred_imgs, mask_imgs = load_pred_gray_and_mask_gray_imgs(folder_path)

    pred_x_list = []
    pred_y_list = []
    mask_x_list = []
    mask_y_list = []
    for idx in range(len(pred_imgs)):
        pred_info = eval_tool.get_calib_ellipse_info2(pred_imgs[idx])
        mask_info = eval_tool.get_calib_ellipse_info2(mask_imgs[idx])

        pred_x, pred_y = None, None
        if pred_info:
            center, w, h, radian = pred_info
            pred_x, pred_y = center
            if w > h:
                r = h/w
            else:
                r = w/h
            
            if roundness:
                if r < roundness:
                    pred_x, pred_y = None, None
            

        mask_x, mask_y = None, None
        if mask_info:
            center, w, h, radian = mask_info
            mask_x, mask_y = center
            if w > h:
                r = h/w
            else:
                r = w/h
            
            if roundness:
                if r < roundness:
                    mask_x, mask_y = None, None  

        mask_x_list.append(mask_x)
        mask_y_list.append(mask_y)
        pred_x_list.append(pred_x)
        pred_y_list.append(pred_y)

    return [list(indices), mask_x_list, mask_y_list, pred_x_list, pred_y_list]


def save_indexed_centers_csv(folder_path:str, roundness:int=None)->None:
    indices, mask_x_list, mask_y_list, pred_x_list, pred_y_list = get_mask_and_pred_centers_with_index(folder_path,roundness)
    fe = FeatureExtractor()
    indices = np.array(indices)
    
    ## ex) grouped_indices = [[100,850], [1000,1750]]
    grouped_indices = fe.get_grouped_sequence(indices)
    
    npa_mask_x = []
    npa_mask_y = []
    npa_pred_x = []
    npa_pred_y = []

    for grouped in grouped_indices:
        start_num, end_num = grouped
        start_index = np.where(indices==start_num)[0]
        end_index = np.where(indices==end_num)[0]
        npa_mask_x = np.append(npa_mask_x, np.array(fe.fill_na(mask_x_list[start_index:end_index+1],'all')))
        npa_mask_y = np.append(npa_mask_y, np.array(fe.fill_na(mask_y_list[start_index:end_index+1],'all')))
        npa_pred_x = np.append(npa_pred_x, np.array(fe.fill_na(pred_x_list[start_index:end_index+1],'all')))
        npa_pred_y = np.append(npa_pred_y, np.array(fe.fill_na(pred_y_list[start_index:end_index+1],'all')))

    with open(f'{os.path.join(folder_path,"indexed_centers").csv}','w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["index", "mask_x", "mask_y", "pred_x", "pred_y"])
        for i in range(len(indices)):
            writer.writerow([indices[i], npa_mask_x[i], npa_mask_y[i], npa_pred_x[i], npa_pred_y[i]])
            
def get_IOUs(pred_imgs:np.ndarray, mask_imgs:np.ndarray)->np.ndarray:
    
    IOUs = []
    for idx, _ in enumerate(mask_imgs):
       IOUs.append(dice_score(mask_imgs[idx]/255,pred_imgs[idx]/255))
    
    return np.array(IOUs)


def get_confusion_matrix_dict(pred_imgs:np.ndarray, mask_imgs:np.ndarray)->dict:
    ## cut-off = 0.3
    TP = 0
    FP = 0
    TN = 0
    FN = 0
    
    IOUs = get_IOUs(pred_imgs, mask_imgs)
    for idx, _ in enumerate(pred_imgs):
        if IOUs[idx] >= 0.70:
            TP += 1
        else:
            pred_sum = np.sum(pred_imgs[idx])
            mask_sum = np.sum(mask_imgs[idx])

            if pred_sum != 0 and mask_sum != 0:
                FN += 1
            elif pred_sum == 0 and mask_sum == 0:
                TN += 1
            elif pred_sum == 0 and mask_sum != 0:
                FN += 1
            elif pred_sum != 0 and mask_sum == 0:
                FP += 1

    return {"TP":TP, "FP":FP, "TN":TN, "FN":FN}


def get_pseudo_y_with_cm(TP:int, FP:int, TN:int, FN:int)->'list[np.ndarray, np.ndarray]':
    ## [ y1, y2 ] = [ y_true, y_pred ]
    
    concat = []

    if TP:
        tp_arr = np.array([1, 1] * TP).reshape(-1,2)
        concat.append(tp_arr)
    if FP:
        fp_arr = np.array([0, 1] * FP).reshape(-1,2)
        concat.append(fp_arr)
    if TN:
        tn_arr = np.array([0, 0] * TN).reshape(-1,2)
        concat.append(tn_arr)
    if FN:
        fn_arr = np.array([1, 0] * FN).reshape(-1,2)
        concat.append(fn_arr)

    result = np.concatenate(concat,axis=0)

    return [result[:,0], result[:,1]]


def get_average_precision_score(y_true:np.ndarray, y_pred:np.ndarray, flag_draw:bool=False) -> float:
    average_precision = average_precision_score(y_true, y_pred)
    if flag_draw:
        precision, recall, threshold = precision_recall_curve(y_true,y_pred)
        display = PrecisionRecallDisplay(precision,recall,average_precision=average_precision)
        display.plot()
        _ = display.ax_.set_title("precision-recall_curve")
        plt.show()
    return average_precision




## copy images from from_folder to to_folder. the index is accumulated
def copy_images(from_folder:str, to_folder:str, flag_predicted_image:bool=True)-> None:
    from_images = glob.glob(os.path.join(from_folder,"*_orig.png"))
    to_images = glob.glob(os.path.join(to_folder,"*_orig.png"))
    from_images_num = len(from_images)
    to_images_num = len(to_images)
    

    for index in range(from_images_num):
        img_orig = cv2.imread(os.path.join(from_folder,f"{index}_orig.png"),cv2.IMREAD_COLOR)
        img_mask = cv2.imread(os.path.join(from_folder,f"{index}_mask.png"),cv2.IMREAD_COLOR)
        cv2.imwrite(os.path.join(to_folder,f"{index+to_images_num}_orig.png"),img_orig)
        cv2.imwrite(os.path.join(to_folder,f"{index+to_images_num}_mask.png"),img_mask)
        if flag_predicted_image:
            img_predicted = cv2.imread(os.path.join(from_folder,f"{index}_predicted.png"),cv2.IMREAD_COLOR)
            cv2.imwrite(os.path.join(to_folder,f"{index+to_images_num}_predicted.png"),img_predicted)
            
if __name__ == '__main__':
    # f_path = "C:\kwoncy\eye\image_datas\\6_sixth_make_roi_with_bad_video_images\\test_with_clean_little_bad_imgs"
    f_path = "C:\kwoncy\eye\image_datas\\6_sixth_make_roi_with_bad_video_images\\test_with_bad_imgs"
    # model_evaluate_with_predicted_images(f_path)
    model_evaluate_with_predicted_images2(f_path)
    # FROM_FOLDER = "C:\kwoncy\eye\image_datas\\6_sixth_make_roi_with_bad_video_images\\test_with_little_bad_imgs" 
    # TO_FOLDER = "C:\kwoncy\eye\image_datas\\6_sixth_make_roi_with_bad_video_images\\test_with_clean_little_bad_imgs" 
    # copy_images(FROM_FOLDER,TO_FOLDER)
    
    # print(2*0.990*0.977/(0.990+0.977))
    # print(2*0.835*0.957/(0.835+0.957))
