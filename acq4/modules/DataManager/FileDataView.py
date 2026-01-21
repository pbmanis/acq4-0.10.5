from typing import Optional

import pyqtgraph as pg
from acq4.filetypes.MultiPatchLog import MultiPatchLogWidget
from acq4.util import Qt
from acq4.util.DataManager import FileHandle
from acq4.util.DictView import DictView

# from pg.graphicsItems import MultiPlotItem as MultiPlotItem
from pg.Qt import QtCore
from pg.widgets.GraphicsView import GraphicsView
from pg.graphicsItems import GraphicsLayout



class MultiPlotItem(GraphicsLayout.GraphicsLayout):
    """
    :class:`~pyqtgraph.GraphicsLayout` that automatically generates a grid of
    plots from a MetaArray.

    .. seealso:: :class:`~pyqtgraph.MultiPlotWidget`: Widget containing a MultiPlotItem
    """

    def __init__(self, *args, **kwds):
        GraphicsLayout.GraphicsLayout.__init__(self, *args, **kwds)
        self.plots = []

    def plot(self, data, **plotArgs):
        """Plot the data from a MetaArray with each array column as a separate
        :class:`~pyqtgraph.PlotItem`.

        Axis labels are automatically extracted from the array info.

        ``plotArgs`` are passed to :meth:`PlotItem.plot
        <pyqtgraph.PlotItem.plot>`.
        """
        #self.layout.clear()

        if hasattr(data, 'implements') and data.implements('MetaArray'):
            if data.ndim != 2:
                raise Exception("MultiPlot currently only accepts 2D MetaArray.")
            ic = data.infoCopy()
            ax = 0
            for i in [0, 1]:
                if 'cols' in ic[i]:
                    ax = i
                    break
            #print "Plotting using axis %d as columns (%d plots)" % (ax, data.shape[ax])
            for i in range(data.shape[ax]):
                pi = self.addPlot()
                self.nextRow()
                sl = [slice(None)] * 2
                sl[ax] = i
                pi.plot(data[tuple(sl)], **plotArgs)
                #self.layout.addItem(pi, i, 0)
                self.plots.append((pi, i, 0))
                info = ic[ax]['cols'][i]
                title = info.get('title', info.get('name', None))
                units = info.get('units', None)
                pi.setLabel('left', text=title, units=units)
            info = ic[1-ax]
            title = info.get('title', info.get('name', None))
            units = info.get('units', None)
            pi.setLabel('bottom', text=title, units=units)
        else:
            raise Exception("Data type %s not (yet?) supported for MultiPlot." % type(data))

    def close(self):
        for p in self.plots:
            p[0].close()
        self.plots = None
        self.clear()

# 
__all__ = ['MultiPlotWidget']
class MultiPlotWidget(GraphicsView):
    """Widget implementing a :class:`~pyqtgraph.GraphicsView` with a single
    :class:`~pyqtgraph.MultiPlotItem` inside."""
    def __init__(self, parent=None):
        self.minPlotHeight = 50
        self.mPlotItem = MultiPlotItem.MultiPlotItem()
        GraphicsView.__init__(self, parent)
        self.enableMouse(False)
        self.setCentralItem(self.mPlotItem)
        ## Explicitly wrap methods from mPlotItem
        #for m in ['setData']:
            #setattr(self, m, getattr(self.mPlotItem, m))
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                
    def __getattr__(self, attr):  ## implicitly wrap methods from plotItem
        if hasattr(self.mPlotItem, attr):
            m = getattr(self.mPlotItem, attr)
            if hasattr(m, '__call__'):
                return m
        raise AttributeError(attr)

    def setMinimumPlotHeight(self, min):
        """Set the minimum height for each sub-plot displayed. 
        
        If the total height of all plots is greater than the height of the 
        widget, then a scroll bar will appear to provide access to the entire
        set of plots.
        
        Added in version 0.9.9
        """
        self.minPlotHeight = min
        self.resizeEvent(None)

    def widgetGroupInterface(self):
        return (None, MultiPlotWidget.saveState, MultiPlotWidget.restoreState)

    def saveState(self):
        return {}
        #return self.plotItem.saveState()
        
    def restoreState(self, state):
        pass
        #return self.plotItem.restoreState(state)

    def close(self):
        self.mPlotItem.close()
        self.mPlotItem = None
        self.setParent(None)
        GraphicsView.close(self)

    def setRange(self, *args, **kwds):
        GraphicsView.setRange(self, *args, **kwds)
        if self.centralWidget is not None:
            r = self.range
            minHeight = len(self.mPlotItem.plots) * self.minPlotHeight
            if r.height() < minHeight:
                r.setHeight(minHeight)
                r.setWidth(r.width() - self.verticalScrollBar().width())
            self.centralWidget.setGeometry(r)

    def resizeEvent(self, ev):
        if self.closed:
            return
        if self.autoPixelRange:
            self.range = QtCore.QRectF(0, 0, self.size().width(), self.size().height())
        MultiPlotWidget.setRange(self, self.range, padding=0, disableAutoPixel=False)  ## we do this because some subclasses like to redefine setRange in an incompatible way.
        self.updateMatrix()



class FileDataView(Qt.QSplitter):
    def __init__(self, parent):
        Qt.QSplitter.__init__(self, parent)
        self.setOrientation(Qt.Qt.Vertical)
        self._current = None
        self._widgets = []
        self._dictWidget = None
        self._cursorText = None
        self._imageWidget: Optional[pg.ImageView] = None
        self._multiPatchLogWidget = None

    def setCurrentFile(self, fh: FileHandle):
        if fh is self._current:
            return
        self._current = fh
        if fh is None or fh.isDir() or (typ := fh.fileType()) is None:
            self.clear()
            return

        with pg.BusyCursor():
            if typ == 'MultiPatchLog':
                self.displayMultiPatchLog(fh)
                return

            data = fh.read()
            if typ == 'ImageFile':
                self.displayDataAsImage(data)
                self.displayMetaInfoForData(data)
            elif typ == 'MetaArray':
                if data.ndim == 2 and not data.axisHasColumns(0) and not data.axisHasColumns(1):
                    self.displayDataAsImage(data)
                elif data.ndim > 2:
                    self.displayDataAsImage(data)
                else:
                    self.displayDataAsPlot(data)
                self.displayMetaInfoForData(data)

    def displayMetaInfoForData(self, data):
        if not hasattr(data, 'implements') or not data.implements('MetaArray'):
            return
        info = data.infoCopy()
        if self._dictWidget is None:
            w = DictView(info)
            self._dictWidget = w
            self.addWidget(w)
            self._widgets.append(w)
            h = self.size().height()
            self.setSizes([int(h * 0.8), int(h * 0.2)])
        else:
            self._dictWidget.setData(info)

    def displayDataAsPlot(self, data):
        self.clear()
        w = pg.MultiPlotWidget(self)
        w.setObjectName("DataManager_multiPlotWidget")
        self.addWidget(w)
        w.plot(data)
        self._widgets.append(w)

    def displayDataAsImage(self, data):
        if self._imageWidget is None:
            self.clear()
            w = pg.ImageView(self)
            self._imageWidget = w
            self._imageWidget.scene.sigMouseMoved.connect(self.noticeMouseMove)
            self._cursorText = pg.TextItem()
            self._imageWidget.scene.addItem(self._cursorText)
            self.addWidget(w)
            self._widgets.append(w)
        self._imageWidget.setImage(data, autoRange=False)

    def noticeMouseMove(self, pos):
        if self._imageWidget is None:
            return
        view = self._imageWidget.getView()
        if not view.sceneBoundingRect().contains(pos):
            return
        self._cursorText.setPos(pos.x() + 12, pos.y())
        pos = view.mapSceneToView(pos)
        self._cursorText.setText(f'({int(pos.x())}, {int(pos.y())})', color='y')

    def displayMultiPatchLog(self, fh):
        self.clear()
        self._multiPatchLogWidget = MultiPatchLogWidget(self)
        self.addWidget(self._multiPatchLogWidget)
        self._widgets.append(self._multiPatchLogWidget)
        self._multiPatchLogWidget.show()
        self._multiPatchLogWidget.addLog(fh)

    def clear(self):
        for w in self._widgets:
            w.close()
            w.setParent(None)
        if self._imageWidget is not None:
            self._imageWidget.scene.sigMouseMoved.disconnect(self.noticeMouseMove)
        self._widgets = []
        self._dictWidget = None
        self._imageWidget = None
        self._cursorText = None
        self._multiPatchLogWidget = None
