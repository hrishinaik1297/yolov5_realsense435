import argparse
import time, os
from pathlib import Path

import cv2
import torch
import torch.backends.cudnn as cudnn
from numpy import random
import pyrealsense2 as rs
import numpy as np

from models.experimental import attempt_load
from utils.dataloaders import LoadStreams, LoadImages
from utils.general import check_img_size, check_requirements, non_max_suppression, apply_classifier,scale_coords, \
    xyxy2xywh, strip_optimizer, set_logging, increment_path
from utils.plots import plot_one_box
from utils.torch_utils import select_device, load_classifier, time_sync

def letterbox(img, new_shape=(640, 640), color=(114, 114, 114), auto=True, scaleFill=False, scaleup=True, stride=32):
    # Resize and pad image while meeting stride-multiple constraints
    shape = img.shape[:2]  # current shape [height, width]
    if isinstance(new_shape, int):
        new_shape = (new_shape, new_shape)

    # Scale ratio (new / old)
    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    if not scaleup:  # only scale down, do not scale up (for better test mAP)
        r = min(r, 1.0)

    # Compute padding
    ratio = r, r  # width, height ratios
    new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
    dw, dh = new_shape[1] - new_unpad[0], new_shape[0] - new_unpad[1]  # wh padding
    if auto:  # minimum rectangle
        dw, dh = np.mod(dw, stride), np.mod(dh, stride)  # wh padding
    elif scaleFill:  # stretch
        dw, dh = 0.0, 0.0
        new_unpad = (new_shape[1], new_shape[0])
        ratio = new_shape[1] / shape[1], new_shape[0] / shape[0]  # width, height ratios

    dw /= 2  # divide padding into 2 sides
    dh /= 2

    if shape[::-1] != new_unpad:  # resize
        img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)  # add border
    return img, ratio, (dw, dh)


def detect(save_img=False):
    
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.color, 1280, 720, rs.format.bgr8, 30)
    ######################################################################
    config.enable_stream(rs.stream.depth, 1280, 720, rs.format.z16, 30)
    #####################################################################
    print("[INFO] Starting streaming...")
    pipeline.start(config)
    print("[INFO] Camera ready.")

    weights, view_img, save_txt, imgsz = opt.weights, opt.view_img, opt.save_txt, opt.img_size
    #webcam = source.isnumeric() or source.endswith('.txt') or source.lower().startswith(
    #    ('rtsp://', 'rtmp://', 'http://'))

    # Directories
    save_dir = Path(increment_path(Path(opt.project) / opt.name, exist_ok=opt.exist_ok))  # increment run
    (save_dir / 'labels' if save_txt else save_dir).mkdir(parents=True, exist_ok=True)  # make dir

    # Initialize
    set_logging()
    device = select_device(opt.device)
    half = device.type != 'cpu'  # half precision only supported on CUDA

    # Load model
    # model = attempt_load(weights='/home/rp01jm/Documents/rockPicker/best.pt', map_location=device)  # load FP32 model
    model = attempt_load(weights=os.path.join(os.getcwd(),'yolov5s.pt'))  # load FP32 model
    model.to(device)
    model.eval()  # Set the model to evaluation mode
    stride = int(model.stride.max())  # model stride
    imgsz = check_img_size(imgsz, s=stride)  # check img_size
    if half:
        model.half()  # to FP16

    # Second-stage classifier
    classify = False
    if classify:
        modelc = load_classifier(name='resnet101', n=2)  # initialize
        modelc.load_state_dict(torch.load('weights/resnet101.pt', map_location=device)['model']).to(device).eval()

    # Set Dataloader
    vid_path, vid_writer = None, None
    
    webcam= False
    if webcam is True:
        view_img = True
        cudnn.benchmark = True  # set True to speed up constant image size inference
        dataset = LoadStreams(source, img_size=imgsz, stride=stride)
    else:
        save_img = True

    # Get names and colors
    names = model.module.names if hasattr(model, 'module') else model.names
    colors = [[random.randint(0, 255) for _ in range(3)] for _ in names]

    # Run inference
    if device.type != 'cpu':
        model(torch.zeros(1, 3, imgsz, imgsz).to(device).type_as(next(model.parameters())))  # run once
    t0 = time.time()

    

    # FPS 
    fps_start_time = time.time()
    fps_counter = 0

    # Initialize variables for object tracking
    prev_centroid_x_mm = None
    prev_centroid_y_mm = None

    
    while True:
    #for path, img, im0s, vid_cap in dataset:
        save_img = True
        path = os.getcwd()
        frames = pipeline.wait_for_frames()
        color_frame = frames.get_color_frame()
        depth = frames.get_depth_frame()

        if not depth: continue

        color_image = np.asanyarray(color_frame.get_data())
        im0s = color_image
        img = letterbox(im0s)[0]
        img = img[:, :, ::-1].transpose(2, 0, 1)  # BGR to RGB, to 3x416x416
        img = np.ascontiguousarray(img)
        img = torch.from_numpy(img).to(device)
        img = img.half() if half else img.float()  # uint8 to fp16/32
        img /= 255.0  # 0 - 255 to 0.0 - 1.0
        if img.ndimension() == 3:
            img = img.unsqueeze(0)

        # Inference
        t1 = time_sync()
        pred = model(img, augment=opt.augment)[0]

        # Apply NMS
        pred = non_max_suppression(pred, opt.conf_thres, opt.iou_thres, classes=opt.classes, agnostic=opt.agnostic_nms)
        t2 = time_sync()

        # Apply Classifier
        if classify:
            pred = apply_classifier(pred, modelc, img, im0s)

        



            
            
        # Process detections
        for i, det in enumerate(pred):  # detections per image
            if webcam:  # batch_size >= 1
                p, s, im0, frame = path[i], '%g: ' % i, im0s[i].copy(), dataset.count
            else:
                p, s, im0 = path, '', im0s #, getattr(dataset, 'frame', 0)

            p = Path(p)  # to Path
            save_path = str(save_dir / p.name)  # img.jpg
            #txt_path = str(save_dir / 'labels' / p.stem) + ('' if dataset.mode == 'image' else f'_{frame}')  # img.txt
            s += '%gx%g ' % img.shape[2:]  # print string
            gn = torch.tensor(im0.shape)[[1, 0, 1, 0]]  # normalization gain whwh
                
            

            if len(det):
                # Rescale boxes from img_size to im0 size
                det[:, :4] = scale_coords(img.shape[2:], det[:, :4], im0.shape).round()

                # Print results
                for c in det[:, -1].unique():
                    n = (det[:, -1] == c).sum()  # detections per class
                    s += f"{n} {names[int(c)]}{'s' * (n > 1)}, "  # add to string

                # Write results
                for *xyxy, conf, cls in reversed(det):
                    if save_txt:  # Write to file
                        xywh = (xyxy2xywh(torch.tensor(xyxy).view(1, 4)) / gn).view(-1).tolist()  # normalized xywh
                        line = (cls, *xywh, conf) if opt.save_conf else (cls, *xywh)  # label format
                        with open(txt_path + '.txt', 'a') as f:
                            f.write(('%g ' * len(line)).rstrip() % line + '\n')



                    # Display FPS 

                    fps_counter += 1
                    if time.time() - fps_start_time >= 1:
                        fps = fps_counter / (time.time() - fps_start_time)
                        fps_start_time = time.time()
                        fps_counter = 0

                        # Display FPS on the screen
                        cv2.putText(im0, f'FPS: {fps:.2f}', (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

                    # Assuming you have a conversion factor: pixels to millimeters
                    conversion_factor = 0.1  # Example conversion factor: 1 pixel = 0.1 mm

                    if save_img or view_img:
                        label = f'{names[int(cls)]} {conf:.2f}'

                        centroid_x = int((xyxy[0] + xyxy[2]) / 2)
                        centroid_y = int((xyxy[1] + xyxy[3]) / 2)
                        centroid_x_mm = centroid_x * conversion_factor
                        centroid_y_mm = centroid_y * conversion_factor

                        radius = 5
                        color = (255, 0, 0)
                        thickness = 3
                        cv2.circle(im0, (centroid_x, centroid_y), radius, color, thickness)

                        font_scale = 0.5
                        font_color = (255, 255, 255)
                        font_thickness = 1
                        text = f'(X: {centroid_x_mm:.2f} mm, Y: {centroid_y_mm:.2f} mm)'
                        text_size, _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness)
                        text_origin = (centroid_x - text_size[0] // 2, centroid_y + text_size[1] // 2)
                        #cv2.putText(im0, text, text_origin, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_color, font_thickness, lineType=cv2.LINE_AA)

                        plot_one_box(xyxy, im0, label=label, color=colors[int(cls)], line_thickness=3)

                        d1, d2 = int((int(xyxy[0]) + int(xyxy[2])) / 2), int((int(xyxy[1]) + int(xyxy[3])) / 2)
                        zDepth = depth.get_distance(d1, d2)
                        zDepth_inches = zDepth * 39.3701
                        zDepth_cm = zDepth * 100

                        depth_text = f'Depth: {zDepth_cm:.2f} cm'
                        depth_origin = (centroid_x - text_size[0] // 2, centroid_y + text_size[1] // 2 + text_size[1])
                        cv2.putText(im0, depth_text, depth_origin, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_color, font_thickness, lineType=cv2.LINE_AA)




                        if prev_centroid_x_mm is not None and prev_centroid_y_mm is not None:
                            # Calculate movement in x and y directions
                            delta_x = centroid_x_mm - prev_centroid_x_mm
                            delta_y = centroid_y_mm - prev_centroid_y_mm

                            # Calculate distance from the frame center
                            frame_center_x = im0.shape[1] / 2  # X-coordinate of the frame center
                            frame_center_y = im0.shape[0] / 2  # Y-coordinate of the frame center
                            distance_from_center_x = centroid_x_mm - (frame_center_x * conversion_factor)
                            distance_from_center_y = centroid_y_mm - (frame_center_y * conversion_factor)

                            # Display distance from center at the center of the object's bounding box
                            distance_message = f'Dist from Center: (X:{distance_from_center_x:.2f} mm, Y:{distance_from_center_y:.2f} mm)'
                            text_size, _ = cv2.getTextSize(distance_message, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness)
                            text_origin = (centroid_x - text_size[0] // 2, centroid_y + text_size[1] // 2)

                            cv2.putText(im0, distance_message, text_origin, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_color, font_thickness, lineType=cv2.LINE_AA)

                        # Update previous centroid coordinates
                        prev_centroid_x_mm = centroid_x_mm
                        prev_centroid_y_mm = centroid_y_mm






                    
                            



        cv2.imshow(str(p), im0)
        if cv2.waitKey(1) == ord('q'):  # q to quit
            break

    pipeline.stop()
    cv2.destroyAllWindows()




   

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--weights', nargs='+', type=str, default='/home/rp01jm/Documents/rockPicker/best.pt', help='model.pt path(s)')
    #parser.add_argument('--source', type=str, default='data/images', help='source')  # file/folder, 0 for webcam
    parser.add_argument('--img-size', type=int, default=640, help='inference size (pixels)')
    parser.add_argument('--conf-thres', type=float, default=0.25, help='object confidence threshold')
    parser.add_argument('--iou-thres', type=float, default=0.45, help='IOU threshold for NMS')
    parser.add_argument('--device', default='', help='cuda device, i.e. 0 or 0,1,2,3 or cpu')
    parser.add_argument('--view-img', action='store_true', help='display results')
    parser.add_argument('--save-txt', action='store_true', help='save results to *.txt')
    parser.add_argument('--save-conf', action='store_true', help='save confidences in --save-txt labels')
    parser.add_argument('--classes', nargs='+', type=int, help='filter by class: --class 0, or --class 0 2 3')
    parser.add_argument('--agnostic-nms', action='store_true', help='class-agnostic NMS')
    parser.add_argument('--augment', action='store_true', help='augmented inference')
    parser.add_argument('--update', action='store_true', help='update all models')
    parser.add_argument('--project', default='runs/detect', help='save results to project/name')
    parser.add_argument('--name', default='exp', help='save results to project/name')
    parser.add_argument('--exist-ok', action='store_true', help='existing project/name ok, do not increment')
    opt = parser.parse_args()
    print(opt)
    check_requirements()

    with torch.no_grad():
        if opt.update:  # update all models (to fix SourceChangeWarning)
            for opt.weights in ['yolov5s.pt', 'yolov5m.pt', 'yolov5l.pt', 'yolov5x.pt']:
                detect()
                strip_optimizer(opt.weights)
        else:
            detect()
