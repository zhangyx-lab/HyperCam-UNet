#!python
# Python Packages
from inspect import isfunction
# PIP Packages
import cv2
import numpy as np
# Project Provided Packages
from util.map_spectral import map_spectral


alphabet = lambda: list(map(chr, range(ord('A'), ord('Z') + 1))) 


def trim(img: np.ndarray, f = lambda a: np.min(a) >= 255)->np.ndarray:
	i = 0; j = 1; k = 0; t = 1
	while f(img[ i, :]): i += 1
	while f(img[-j, :]): j += 1
	while f(img[:,  k]): k += 1
	while f(img[:, -t]): t += 1
	return img[i:-j, k:-t]


def rgb(gray: np.ndarray):
	return np.stack([gray for _ in range(3)], axis=2)


def diff(a: np.ndarray, b: np.ndarray):
	# Compute diff image
	R = (a - b) * (a > b)
	B = (b - a) * (b > a)
	G = np.zeros(R.shape, dtype=np.uint8)
	return np.stack((B, G, R), axis=2)


def text(
		img, text, pos, color=(255, 255, 255),
		font=cv2.FONT_HERSHEY_TRIPLEX,
		scale=0.5, w=1
	):
	img = np.ascontiguousarray(img, dtype=np.uint8)
	return cv2.putText(img, text, pos, font, scale, color, w, cv2.LINE_AA)


def marker(img, pos, color, style=cv2.MARKER_CROSS, size=12, weight=1):
	return cv2.drawMarker(img, pos, color, style, size, weight)


def view(name, imGrid, margin=16, cursorNames: list[str]=alphabet()[::-1], callback=None):
	# Initialize parameters
	h, w, d = imGrid[0][0].shape
	band_number = 0
	cursors = []
	preview = None
	# Text overlay style defaults
	text_pos = (10, h-10)
	# Initialize margin filler
	h_blank = (margin, w, 3)
	h_blank = np.zeros(h_blank, np.uint8) + 255
	v_blank = (2 * h + margin, margin, 3)
	v_blank = np.zeros(v_blank, np.uint8) + 255
	# Generates new image matrix
	def rasterize(export = False):
		nonlocal band_number, margin
		grid = []
		for img, txt, color in imGrid:
			if isfunction(img): img = img(band_number if not export else None)
			elif not export: img = rgb(img[:, :, band_number].copy())
			else: img = map_spectral(img)
			# Render image title text
			img = text(img, txt, text_pos, color)
			# Render selection markers
			for c_id, c_pos in cursors:
				tx, ty = c_pos
				img = text(img, c_id, (tx+5, ty-5), color)
				img = marker(img, c_pos, color)
			# Render preview markers
			if preview is not None:
				img = marker(img, preview, color)
			# Store image into grid list
			grid.append(img)
		# Combine images into grid view
		a, b, c, d = grid
		cols = [
			np.concatenate([a, h_blank, b], axis=0),
			v_blank,
			np.concatenate([c, h_blank, d], axis=0)
		]
		return np.concatenate(cols, axis=1), band_number if export else None
	# Draws rasterized image buffer to window
	def render(i = None):
		nonlocal band_number
		if i is not None: band_number = i
		cv2.imshow(name, rasterize()[0])
	# Updates the cursor object list
	def update_cursor(pos, confirm=False, hasPadding=True):
		nonlocal cursors, preview
		id = None
		if pos is not None:
			x, y = pos
			if hasPadding:
				x = x % (w + margin)
				y = y % (h + margin)
			pos = x, y
			if (x < w and y < h):
				preview = (x, y)
				if confirm:
					id = cursorNames.pop()
					cursors.append((id, preview))
			else:
				preview = None
				pos = None
		else:
			preview = None
		render()
		return id, pos
	# Start window thread
	cv2.namedWindow(name, cv2.WINDOW_AUTOSIZE)
	cv2.startWindowThread()
	cv2.setWindowProperty(name, cv2.WND_PROP_TOPMOST, 1)
	cv2.createTrackbar('band', name, 150, d-1, render)
	if callback is not None: cv2.setMouseCallback(name, callback)
	render()
	# Return all callbacks
	return rasterize, update_cursor, render
