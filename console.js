// ==================== Vendored QR 库（MIT，本地化内嵌） ====================
// ① qrcode-generator 1.4.4（Kazuhiko Arase，MIT）——桌面端二维码生成
// ② jsQR 1.4.0（Cozmo，MIT）——手机端扫码解码（getUserMedia+canvas）
// 来源 npmmirror/jsdelivr；内嵌避免新增静态文件与外网依赖。
//---------------------------------------------------------------------
//
// QR Code Generator for JavaScript
//
// Copyright (c) 2009 Kazuhiko Arase
//
// URL: http://www.d-project.com/
//
// Licensed under the MIT license:
//  http://www.opensource.org/licenses/mit-license.php
//
// The word 'QR Code' is registered trademark of
// DENSO WAVE INCORPORATED
//  http://www.denso-wave.com/qrcode/faqpatent-e.html
//
//---------------------------------------------------------------------

var qrcode = function() {

  //---------------------------------------------------------------------
  // qrcode
  //---------------------------------------------------------------------

  /**
   * qrcode
   * @param typeNumber 1 to 40
   * @param errorCorrectionLevel 'L','M','Q','H'
   */
  var qrcode = function(typeNumber, errorCorrectionLevel) {

    var PAD0 = 0xEC;
    var PAD1 = 0x11;

    var _typeNumber = typeNumber;
    var _errorCorrectionLevel = QRErrorCorrectionLevel[errorCorrectionLevel];
    var _modules = null;
    var _moduleCount = 0;
    var _dataCache = null;
    var _dataList = [];

    var _this = {};

    var makeImpl = function(test, maskPattern) {

      _moduleCount = _typeNumber * 4 + 17;
      _modules = function(moduleCount) {
        var modules = new Array(moduleCount);
        for (var row = 0; row < moduleCount; row += 1) {
          modules[row] = new Array(moduleCount);
          for (var col = 0; col < moduleCount; col += 1) {
            modules[row][col] = null;
          }
        }
        return modules;
      }(_moduleCount);

      setupPositionProbePattern(0, 0);
      setupPositionProbePattern(_moduleCount - 7, 0);
      setupPositionProbePattern(0, _moduleCount - 7);
      setupPositionAdjustPattern();
      setupTimingPattern();
      setupTypeInfo(test, maskPattern);

      if (_typeNumber >= 7) {
        setupTypeNumber(test);
      }

      if (_dataCache == null) {
        _dataCache = createData(_typeNumber, _errorCorrectionLevel, _dataList);
      }

      mapData(_dataCache, maskPattern);
    };

    var setupPositionProbePattern = function(row, col) {

      for (var r = -1; r <= 7; r += 1) {

        if (row + r <= -1 || _moduleCount <= row + r) continue;

        for (var c = -1; c <= 7; c += 1) {

          if (col + c <= -1 || _moduleCount <= col + c) continue;

          if ( (0 <= r && r <= 6 && (c == 0 || c == 6) )
              || (0 <= c && c <= 6 && (r == 0 || r == 6) )
              || (2 <= r && r <= 4 && 2 <= c && c <= 4) ) {
            _modules[row + r][col + c] = true;
          } else {
            _modules[row + r][col + c] = false;
          }
        }
      }
    };

    var getBestMaskPattern = function() {

      var minLostPoint = 0;
      var pattern = 0;

      for (var i = 0; i < 8; i += 1) {

        makeImpl(true, i);

        var lostPoint = QRUtil.getLostPoint(_this);

        if (i == 0 || minLostPoint > lostPoint) {
          minLostPoint = lostPoint;
          pattern = i;
        }
      }

      return pattern;
    };

    var setupTimingPattern = function() {

      for (var r = 8; r < _moduleCount - 8; r += 1) {
        if (_modules[r][6] != null) {
          continue;
        }
        _modules[r][6] = (r % 2 == 0);
      }

      for (var c = 8; c < _moduleCount - 8; c += 1) {
        if (_modules[6][c] != null) {
          continue;
        }
        _modules[6][c] = (c % 2 == 0);
      }
    };

    var setupPositionAdjustPattern = function() {

      var pos = QRUtil.getPatternPosition(_typeNumber);

      for (var i = 0; i < pos.length; i += 1) {

        for (var j = 0; j < pos.length; j += 1) {

          var row = pos[i];
          var col = pos[j];

          if (_modules[row][col] != null) {
            continue;
          }

          for (var r = -2; r <= 2; r += 1) {

            for (var c = -2; c <= 2; c += 1) {

              if (r == -2 || r == 2 || c == -2 || c == 2
                  || (r == 0 && c == 0) ) {
                _modules[row + r][col + c] = true;
              } else {
                _modules[row + r][col + c] = false;
              }
            }
          }
        }
      }
    };

    var setupTypeNumber = function(test) {

      var bits = QRUtil.getBCHTypeNumber(_typeNumber);

      for (var i = 0; i < 18; i += 1) {
        var mod = (!test && ( (bits >> i) & 1) == 1);
        _modules[Math.floor(i / 3)][i % 3 + _moduleCount - 8 - 3] = mod;
      }

      for (var i = 0; i < 18; i += 1) {
        var mod = (!test && ( (bits >> i) & 1) == 1);
        _modules[i % 3 + _moduleCount - 8 - 3][Math.floor(i / 3)] = mod;
      }
    };

    var setupTypeInfo = function(test, maskPattern) {

      var data = (_errorCorrectionLevel << 3) | maskPattern;
      var bits = QRUtil.getBCHTypeInfo(data);

      // vertical
      for (var i = 0; i < 15; i += 1) {

        var mod = (!test && ( (bits >> i) & 1) == 1);

        if (i < 6) {
          _modules[i][8] = mod;
        } else if (i < 8) {
          _modules[i + 1][8] = mod;
        } else {
          _modules[_moduleCount - 15 + i][8] = mod;
        }
      }

      // horizontal
      for (var i = 0; i < 15; i += 1) {

        var mod = (!test && ( (bits >> i) & 1) == 1);

        if (i < 8) {
          _modules[8][_moduleCount - i - 1] = mod;
        } else if (i < 9) {
          _modules[8][15 - i - 1 + 1] = mod;
        } else {
          _modules[8][15 - i - 1] = mod;
        }
      }

      // fixed module
      _modules[_moduleCount - 8][8] = (!test);
    };

    var mapData = function(data, maskPattern) {

      var inc = -1;
      var row = _moduleCount - 1;
      var bitIndex = 7;
      var byteIndex = 0;
      var maskFunc = QRUtil.getMaskFunction(maskPattern);

      for (var col = _moduleCount - 1; col > 0; col -= 2) {

        if (col == 6) col -= 1;

        while (true) {

          for (var c = 0; c < 2; c += 1) {

            if (_modules[row][col - c] == null) {

              var dark = false;

              if (byteIndex < data.length) {
                dark = ( ( (data[byteIndex] >>> bitIndex) & 1) == 1);
              }

              var mask = maskFunc(row, col - c);

              if (mask) {
                dark = !dark;
              }

              _modules[row][col - c] = dark;
              bitIndex -= 1;

              if (bitIndex == -1) {
                byteIndex += 1;
                bitIndex = 7;
              }
            }
          }

          row += inc;

          if (row < 0 || _moduleCount <= row) {
            row -= inc;
            inc = -inc;
            break;
          }
        }
      }
    };

    var createBytes = function(buffer, rsBlocks) {

      var offset = 0;

      var maxDcCount = 0;
      var maxEcCount = 0;

      var dcdata = new Array(rsBlocks.length);
      var ecdata = new Array(rsBlocks.length);

      for (var r = 0; r < rsBlocks.length; r += 1) {

        var dcCount = rsBlocks[r].dataCount;
        var ecCount = rsBlocks[r].totalCount - dcCount;

        maxDcCount = Math.max(maxDcCount, dcCount);
        maxEcCount = Math.max(maxEcCount, ecCount);

        dcdata[r] = new Array(dcCount);

        for (var i = 0; i < dcdata[r].length; i += 1) {
          dcdata[r][i] = 0xff & buffer.getBuffer()[i + offset];
        }
        offset += dcCount;

        var rsPoly = QRUtil.getErrorCorrectPolynomial(ecCount);
        var rawPoly = qrPolynomial(dcdata[r], rsPoly.getLength() - 1);

        var modPoly = rawPoly.mod(rsPoly);
        ecdata[r] = new Array(rsPoly.getLength() - 1);
        for (var i = 0; i < ecdata[r].length; i += 1) {
          var modIndex = i + modPoly.getLength() - ecdata[r].length;
          ecdata[r][i] = (modIndex >= 0)? modPoly.getAt(modIndex) : 0;
        }
      }

      var totalCodeCount = 0;
      for (var i = 0; i < rsBlocks.length; i += 1) {
        totalCodeCount += rsBlocks[i].totalCount;
      }

      var data = new Array(totalCodeCount);
      var index = 0;

      for (var i = 0; i < maxDcCount; i += 1) {
        for (var r = 0; r < rsBlocks.length; r += 1) {
          if (i < dcdata[r].length) {
            data[index] = dcdata[r][i];
            index += 1;
          }
        }
      }

      for (var i = 0; i < maxEcCount; i += 1) {
        for (var r = 0; r < rsBlocks.length; r += 1) {
          if (i < ecdata[r].length) {
            data[index] = ecdata[r][i];
            index += 1;
          }
        }
      }

      return data;
    };

    var createData = function(typeNumber, errorCorrectionLevel, dataList) {

      var rsBlocks = QRRSBlock.getRSBlocks(typeNumber, errorCorrectionLevel);

      var buffer = qrBitBuffer();

      for (var i = 0; i < dataList.length; i += 1) {
        var data = dataList[i];
        buffer.put(data.getMode(), 4);
        buffer.put(data.getLength(), QRUtil.getLengthInBits(data.getMode(), typeNumber) );
        data.write(buffer);
      }

      // calc num max data.
      var totalDataCount = 0;
      for (var i = 0; i < rsBlocks.length; i += 1) {
        totalDataCount += rsBlocks[i].dataCount;
      }

      if (buffer.getLengthInBits() > totalDataCount * 8) {
        throw 'code length overflow. ('
          + buffer.getLengthInBits()
          + '>'
          + totalDataCount * 8
          + ')';
      }

      // end code
      if (buffer.getLengthInBits() + 4 <= totalDataCount * 8) {
        buffer.put(0, 4);
      }

      // padding
      while (buffer.getLengthInBits() % 8 != 0) {
        buffer.putBit(false);
      }

      // padding
      while (true) {

        if (buffer.getLengthInBits() >= totalDataCount * 8) {
          break;
        }
        buffer.put(PAD0, 8);

        if (buffer.getLengthInBits() >= totalDataCount * 8) {
          break;
        }
        buffer.put(PAD1, 8);
      }

      return createBytes(buffer, rsBlocks);
    };

    _this.addData = function(data, mode) {

      mode = mode || 'Byte';

      var newData = null;

      switch(mode) {
      case 'Numeric' :
        newData = qrNumber(data);
        break;
      case 'Alphanumeric' :
        newData = qrAlphaNum(data);
        break;
      case 'Byte' :
        newData = qr8BitByte(data);
        break;
      case 'Kanji' :
        newData = qrKanji(data);
        break;
      default :
        throw 'mode:' + mode;
      }

      _dataList.push(newData);
      _dataCache = null;
    };

    _this.isDark = function(row, col) {
      if (row < 0 || _moduleCount <= row || col < 0 || _moduleCount <= col) {
        throw row + ',' + col;
      }
      return _modules[row][col];
    };

    _this.getModuleCount = function() {
      return _moduleCount;
    };

    _this.make = function() {
      if (_typeNumber < 1) {
        var typeNumber = 1;

        for (; typeNumber < 40; typeNumber++) {
          var rsBlocks = QRRSBlock.getRSBlocks(typeNumber, _errorCorrectionLevel);
          var buffer = qrBitBuffer();

          for (var i = 0; i < _dataList.length; i++) {
            var data = _dataList[i];
            buffer.put(data.getMode(), 4);
            buffer.put(data.getLength(), QRUtil.getLengthInBits(data.getMode(), typeNumber) );
            data.write(buffer);
          }

          var totalDataCount = 0;
          for (var i = 0; i < rsBlocks.length; i++) {
            totalDataCount += rsBlocks[i].dataCount;
          }

          if (buffer.getLengthInBits() <= totalDataCount * 8) {
            break;
          }
        }

        _typeNumber = typeNumber;
      }

      makeImpl(false, getBestMaskPattern() );
    };

    _this.createTableTag = function(cellSize, margin) {

      cellSize = cellSize || 2;
      margin = (typeof margin == 'undefined')? cellSize * 4 : margin;

      var qrHtml = '';

      qrHtml += '<table style="';
      qrHtml += ' border-width: 0px; border-style: none;';
      qrHtml += ' border-collapse: collapse;';
      qrHtml += ' padding: 0px; margin: ' + margin + 'px;';
      qrHtml += '">';
      qrHtml += '<tbody>';

      for (var r = 0; r < _this.getModuleCount(); r += 1) {

        qrHtml += '<tr>';

        for (var c = 0; c < _this.getModuleCount(); c += 1) {
          qrHtml += '<td style="';
          qrHtml += ' border-width: 0px; border-style: none;';
          qrHtml += ' border-collapse: collapse;';
          qrHtml += ' padding: 0px; margin: 0px;';
          qrHtml += ' width: ' + cellSize + 'px;';
          qrHtml += ' height: ' + cellSize + 'px;';
          qrHtml += ' background-color: ';
          qrHtml += _this.isDark(r, c)? '#000000' : '#ffffff';
          qrHtml += ';';
          qrHtml += '"/>';
        }

        qrHtml += '</tr>';
      }

      qrHtml += '</tbody>';
      qrHtml += '</table>';

      return qrHtml;
    };

    _this.createSvgTag = function(cellSize, margin, alt, title) {

      var opts = {};
      if (typeof arguments[0] == 'object') {
        // Called by options.
        opts = arguments[0];
        // overwrite cellSize and margin.
        cellSize = opts.cellSize;
        margin = opts.margin;
        alt = opts.alt;
        title = opts.title;
      }

      cellSize = cellSize || 2;
      margin = (typeof margin == 'undefined')? cellSize * 4 : margin;

      // Compose alt property surrogate
      alt = (typeof alt === 'string') ? {text: alt} : alt || {};
      alt.text = alt.text || null;
      alt.id = (alt.text) ? alt.id || 'qrcode-description' : null;

      // Compose title property surrogate
      title = (typeof title === 'string') ? {text: title} : title || {};
      title.text = title.text || null;
      title.id = (title.text) ? title.id || 'qrcode-title' : null;

      var size = _this.getModuleCount() * cellSize + margin * 2;
      var c, mc, r, mr, qrSvg='', rect;

      rect = 'l' + cellSize + ',0 0,' + cellSize +
        ' -' + cellSize + ',0 0,-' + cellSize + 'z ';

      qrSvg += '<svg version="1.1" xmlns="http://www.w3.org/2000/svg"';
      qrSvg += !opts.scalable ? ' width="' + size + 'px" height="' + size + 'px"' : '';
      qrSvg += ' viewBox="0 0 ' + size + ' ' + size + '" ';
      qrSvg += ' preserveAspectRatio="xMinYMin meet"';
      qrSvg += (title.text || alt.text) ? ' role="img" aria-labelledby="' +
          escapeXml([title.id, alt.id].join(' ').trim() ) + '"' : '';
      qrSvg += '>';
      qrSvg += (title.text) ? '<title id="' + escapeXml(title.id) + '">' +
          escapeXml(title.text) + '</title>' : '';
      qrSvg += (alt.text) ? '<description id="' + escapeXml(alt.id) + '">' +
          escapeXml(alt.text) + '</description>' : '';
      qrSvg += '<rect width="100%" height="100%" fill="white" cx="0" cy="0"/>';
      qrSvg += '<path d="';

      for (r = 0; r < _this.getModuleCount(); r += 1) {
        mr = r * cellSize + margin;
        for (c = 0; c < _this.getModuleCount(); c += 1) {
          if (_this.isDark(r, c) ) {
            mc = c*cellSize+margin;
            qrSvg += 'M' + mc + ',' + mr + rect;
          }
        }
      }

      qrSvg += '" stroke="transparent" fill="black"/>';
      qrSvg += '</svg>';

      return qrSvg;
    };

    _this.createDataURL = function(cellSize, margin) {

      cellSize = cellSize || 2;
      margin = (typeof margin == 'undefined')? cellSize * 4 : margin;

      var size = _this.getModuleCount() * cellSize + margin * 2;
      var min = margin;
      var max = size - margin;

      return createDataURL(size, size, function(x, y) {
        if (min <= x && x < max && min <= y && y < max) {
          var c = Math.floor( (x - min) / cellSize);
          var r = Math.floor( (y - min) / cellSize);
          return _this.isDark(r, c)? 0 : 1;
        } else {
          return 1;
        }
      } );
    };

    _this.createImgTag = function(cellSize, margin, alt) {

      cellSize = cellSize || 2;
      margin = (typeof margin == 'undefined')? cellSize * 4 : margin;

      var size = _this.getModuleCount() * cellSize + margin * 2;

      var img = '';
      img += '<img';
      img += '\u0020src="';
      img += _this.createDataURL(cellSize, margin);
      img += '"';
      img += '\u0020width="';
      img += size;
      img += '"';
      img += '\u0020height="';
      img += size;
      img += '"';
      if (alt) {
        img += '\u0020alt="';
        img += escapeXml(alt);
        img += '"';
      }
      img += '/>';

      return img;
    };

    var escapeXml = function(s) {
      var escaped = '';
      for (var i = 0; i < s.length; i += 1) {
        var c = s.charAt(i);
        switch(c) {
        case '<': escaped += '&lt;'; break;
        case '>': escaped += '&gt;'; break;
        case '&': escaped += '&amp;'; break;
        case '"': escaped += '&quot;'; break;
        default : escaped += c; break;
        }
      }
      return escaped;
    };

    var _createHalfASCII = function(margin) {
      var cellSize = 1;
      margin = (typeof margin == 'undefined')? cellSize * 2 : margin;

      var size = _this.getModuleCount() * cellSize + margin * 2;
      var min = margin;
      var max = size - margin;

      var y, x, r1, r2, p;

      var blocks = {
        '██': '█',
        '█ ': '▀',
        ' █': '▄',
        '  ': ' '
      };

      var blocksLastLineNoMargin = {
        '██': '▀',
        '█ ': '▀',
        ' █': ' ',
        '  ': ' '
      };

      var ascii = '';
      for (y = 0; y < size; y += 2) {
        r1 = Math.floor((y - min) / cellSize);
        r2 = Math.floor((y + 1 - min) / cellSize);
        for (x = 0; x < size; x += 1) {
          p = '█';

          if (min <= x && x < max && min <= y && y < max && _this.isDark(r1, Math.floor((x - min) / cellSize))) {
            p = ' ';
          }

          if (min <= x && x < max && min <= y+1 && y+1 < max && _this.isDark(r2, Math.floor((x - min) / cellSize))) {
            p += ' ';
          }
          else {
            p += '█';
          }

          // Output 2 characters per pixel, to create full square. 1 character per pixels gives only half width of square.
          ascii += (margin < 1 && y+1 >= max) ? blocksLastLineNoMargin[p] : blocks[p];
        }

        ascii += '\n';
      }

      if (size % 2 && margin > 0) {
        return ascii.substring(0, ascii.length - size - 1) + Array(size+1).join('▀');
      }

      return ascii.substring(0, ascii.length-1);
    };

    _this.createASCII = function(cellSize, margin) {
      cellSize = cellSize || 1;

      if (cellSize < 2) {
        return _createHalfASCII(margin);
      }

      cellSize -= 1;
      margin = (typeof margin == 'undefined')? cellSize * 2 : margin;

      var size = _this.getModuleCount() * cellSize + margin * 2;
      var min = margin;
      var max = size - margin;

      var y, x, r, p;

      var white = Array(cellSize+1).join('██');
      var black = Array(cellSize+1).join('  ');

      var ascii = '';
      var line = '';
      for (y = 0; y < size; y += 1) {
        r = Math.floor( (y - min) / cellSize);
        line = '';
        for (x = 0; x < size; x += 1) {
          p = 1;

          if (min <= x && x < max && min <= y && y < max && _this.isDark(r, Math.floor((x - min) / cellSize))) {
            p = 0;
          }

          // Output 2 characters per pixel, to create full square. 1 character per pixels gives only half width of square.
          line += p ? white : black;
        }

        for (r = 0; r < cellSize; r += 1) {
          ascii += line + '\n';
        }
      }

      return ascii.substring(0, ascii.length-1);
    };

    _this.renderTo2dContext = function(context, cellSize) {
      cellSize = cellSize || 2;
      var length = _this.getModuleCount();
      for (var row = 0; row < length; row++) {
        for (var col = 0; col < length; col++) {
          context.fillStyle = _this.isDark(row, col) ? 'black' : 'white';
          context.fillRect(row * cellSize, col * cellSize, cellSize, cellSize);
        }
      }
    }

    return _this;
  };

  //---------------------------------------------------------------------
  // qrcode.stringToBytes
  //---------------------------------------------------------------------

  qrcode.stringToBytesFuncs = {
    'default' : function(s) {
      var bytes = [];
      for (var i = 0; i < s.length; i += 1) {
        var c = s.charCodeAt(i);
        bytes.push(c & 0xff);
      }
      return bytes;
    }
  };

  qrcode.stringToBytes = qrcode.stringToBytesFuncs['default'];

  //---------------------------------------------------------------------
  // qrcode.createStringToBytes
  //---------------------------------------------------------------------

  /**
   * @param unicodeData base64 string of byte array.
   * [16bit Unicode],[16bit Bytes], ...
   * @param numChars
   */
  qrcode.createStringToBytes = function(unicodeData, numChars) {

    // create conversion map.

    var unicodeMap = function() {

      var bin = base64DecodeInputStream(unicodeData);
      var read = function() {
        var b = bin.read();
        if (b == -1) throw 'eof';
        return b;
      };

      var count = 0;
      var unicodeMap = {};
      while (true) {
        var b0 = bin.read();
        if (b0 == -1) break;
        var b1 = read();
        var b2 = read();
        var b3 = read();
        var k = String.fromCharCode( (b0 << 8) | b1);
        var v = (b2 << 8) | b3;
        unicodeMap[k] = v;
        count += 1;
      }
      if (count != numChars) {
        throw count + ' != ' + numChars;
      }

      return unicodeMap;
    }();

    var unknownChar = '?'.charCodeAt(0);

    return function(s) {
      var bytes = [];
      for (var i = 0; i < s.length; i += 1) {
        var c = s.charCodeAt(i);
        if (c < 128) {
          bytes.push(c);
        } else {
          var b = unicodeMap[s.charAt(i)];
          if (typeof b == 'number') {
            if ( (b & 0xff) == b) {
              // 1byte
              bytes.push(b);
            } else {
              // 2bytes
              bytes.push(b >>> 8);
              bytes.push(b & 0xff);
            }
          } else {
            bytes.push(unknownChar);
          }
        }
      }
      return bytes;
    };
  };

  //---------------------------------------------------------------------
  // QRMode
  //---------------------------------------------------------------------

  var QRMode = {
    MODE_NUMBER :    1 << 0,
    MODE_ALPHA_NUM : 1 << 1,
    MODE_8BIT_BYTE : 1 << 2,
    MODE_KANJI :     1 << 3
  };

  //---------------------------------------------------------------------
  // QRErrorCorrectionLevel
  //---------------------------------------------------------------------

  var QRErrorCorrectionLevel = {
    L : 1,
    M : 0,
    Q : 3,
    H : 2
  };

  //---------------------------------------------------------------------
  // QRMaskPattern
  //---------------------------------------------------------------------

  var QRMaskPattern = {
    PATTERN000 : 0,
    PATTERN001 : 1,
    PATTERN010 : 2,
    PATTERN011 : 3,
    PATTERN100 : 4,
    PATTERN101 : 5,
    PATTERN110 : 6,
    PATTERN111 : 7
  };

  //---------------------------------------------------------------------
  // QRUtil
  //---------------------------------------------------------------------

  var QRUtil = function() {

    var PATTERN_POSITION_TABLE = [
      [],
      [6, 18],
      [6, 22],
      [6, 26],
      [6, 30],
      [6, 34],
      [6, 22, 38],
      [6, 24, 42],
      [6, 26, 46],
      [6, 28, 50],
      [6, 30, 54],
      [6, 32, 58],
      [6, 34, 62],
      [6, 26, 46, 66],
      [6, 26, 48, 70],
      [6, 26, 50, 74],
      [6, 30, 54, 78],
      [6, 30, 56, 82],
      [6, 30, 58, 86],
      [6, 34, 62, 90],
      [6, 28, 50, 72, 94],
      [6, 26, 50, 74, 98],
      [6, 30, 54, 78, 102],
      [6, 28, 54, 80, 106],
      [6, 32, 58, 84, 110],
      [6, 30, 58, 86, 114],
      [6, 34, 62, 90, 118],
      [6, 26, 50, 74, 98, 122],
      [6, 30, 54, 78, 102, 126],
      [6, 26, 52, 78, 104, 130],
      [6, 30, 56, 82, 108, 134],
      [6, 34, 60, 86, 112, 138],
      [6, 30, 58, 86, 114, 142],
      [6, 34, 62, 90, 118, 146],
      [6, 30, 54, 78, 102, 126, 150],
      [6, 24, 50, 76, 102, 128, 154],
      [6, 28, 54, 80, 106, 132, 158],
      [6, 32, 58, 84, 110, 136, 162],
      [6, 26, 54, 82, 110, 138, 166],
      [6, 30, 58, 86, 114, 142, 170]
    ];
    var G15 = (1 << 10) | (1 << 8) | (1 << 5) | (1 << 4) | (1 << 2) | (1 << 1) | (1 << 0);
    var G18 = (1 << 12) | (1 << 11) | (1 << 10) | (1 << 9) | (1 << 8) | (1 << 5) | (1 << 2) | (1 << 0);
    var G15_MASK = (1 << 14) | (1 << 12) | (1 << 10) | (1 << 4) | (1 << 1);

    var _this = {};

    var getBCHDigit = function(data) {
      var digit = 0;
      while (data != 0) {
        digit += 1;
        data >>>= 1;
      }
      return digit;
    };

    _this.getBCHTypeInfo = function(data) {
      var d = data << 10;
      while (getBCHDigit(d) - getBCHDigit(G15) >= 0) {
        d ^= (G15 << (getBCHDigit(d) - getBCHDigit(G15) ) );
      }
      return ( (data << 10) | d) ^ G15_MASK;
    };

    _this.getBCHTypeNumber = function(data) {
      var d = data << 12;
      while (getBCHDigit(d) - getBCHDigit(G18) >= 0) {
        d ^= (G18 << (getBCHDigit(d) - getBCHDigit(G18) ) );
      }
      return (data << 12) | d;
    };

    _this.getPatternPosition = function(typeNumber) {
      return PATTERN_POSITION_TABLE[typeNumber - 1];
    };

    _this.getMaskFunction = function(maskPattern) {

      switch (maskPattern) {

      case QRMaskPattern.PATTERN000 :
        return function(i, j) { return (i + j) % 2 == 0; };
      case QRMaskPattern.PATTERN001 :
        return function(i, j) { return i % 2 == 0; };
      case QRMaskPattern.PATTERN010 :
        return function(i, j) { return j % 3 == 0; };
      case QRMaskPattern.PATTERN011 :
        return function(i, j) { return (i + j) % 3 == 0; };
      case QRMaskPattern.PATTERN100 :
        return function(i, j) { return (Math.floor(i / 2) + Math.floor(j / 3) ) % 2 == 0; };
      case QRMaskPattern.PATTERN101 :
        return function(i, j) { return (i * j) % 2 + (i * j) % 3 == 0; };
      case QRMaskPattern.PATTERN110 :
        return function(i, j) { return ( (i * j) % 2 + (i * j) % 3) % 2 == 0; };
      case QRMaskPattern.PATTERN111 :
        return function(i, j) { return ( (i * j) % 3 + (i + j) % 2) % 2 == 0; };

      default :
        throw 'bad maskPattern:' + maskPattern;
      }
    };

    _this.getErrorCorrectPolynomial = function(errorCorrectLength) {
      var a = qrPolynomial([1], 0);
      for (var i = 0; i < errorCorrectLength; i += 1) {
        a = a.multiply(qrPolynomial([1, QRMath.gexp(i)], 0) );
      }
      return a;
    };

    _this.getLengthInBits = function(mode, type) {

      if (1 <= type && type < 10) {

        // 1 - 9

        switch(mode) {
        case QRMode.MODE_NUMBER    : return 10;
        case QRMode.MODE_ALPHA_NUM : return 9;
        case QRMode.MODE_8BIT_BYTE : return 8;
        case QRMode.MODE_KANJI     : return 8;
        default :
          throw 'mode:' + mode;
        }

      } else if (type < 27) {

        // 10 - 26

        switch(mode) {
        case QRMode.MODE_NUMBER    : return 12;
        case QRMode.MODE_ALPHA_NUM : return 11;
        case QRMode.MODE_8BIT_BYTE : return 16;
        case QRMode.MODE_KANJI     : return 10;
        default :
          throw 'mode:' + mode;
        }

      } else if (type < 41) {

        // 27 - 40

        switch(mode) {
        case QRMode.MODE_NUMBER    : return 14;
        case QRMode.MODE_ALPHA_NUM : return 13;
        case QRMode.MODE_8BIT_BYTE : return 16;
        case QRMode.MODE_KANJI     : return 12;
        default :
          throw 'mode:' + mode;
        }

      } else {
        throw 'type:' + type;
      }
    };

    _this.getLostPoint = function(qrcode) {

      var moduleCount = qrcode.getModuleCount();

      var lostPoint = 0;

      // LEVEL1

      for (var row = 0; row < moduleCount; row += 1) {
        for (var col = 0; col < moduleCount; col += 1) {

          var sameCount = 0;
          var dark = qrcode.isDark(row, col);

          for (var r = -1; r <= 1; r += 1) {

            if (row + r < 0 || moduleCount <= row + r) {
              continue;
            }

            for (var c = -1; c <= 1; c += 1) {

              if (col + c < 0 || moduleCount <= col + c) {
                continue;
              }

              if (r == 0 && c == 0) {
                continue;
              }

              if (dark == qrcode.isDark(row + r, col + c) ) {
                sameCount += 1;
              }
            }
          }

          if (sameCount > 5) {
            lostPoint += (3 + sameCount - 5);
          }
        }
      };

      // LEVEL2

      for (var row = 0; row < moduleCount - 1; row += 1) {
        for (var col = 0; col < moduleCount - 1; col += 1) {
          var count = 0;
          if (qrcode.isDark(row, col) ) count += 1;
          if (qrcode.isDark(row + 1, col) ) count += 1;
          if (qrcode.isDark(row, col + 1) ) count += 1;
          if (qrcode.isDark(row + 1, col + 1) ) count += 1;
          if (count == 0 || count == 4) {
            lostPoint += 3;
          }
        }
      }

      // LEVEL3

      for (var row = 0; row < moduleCount; row += 1) {
        for (var col = 0; col < moduleCount - 6; col += 1) {
          if (qrcode.isDark(row, col)
              && !qrcode.isDark(row, col + 1)
              &&  qrcode.isDark(row, col + 2)
              &&  qrcode.isDark(row, col + 3)
              &&  qrcode.isDark(row, col + 4)
              && !qrcode.isDark(row, col + 5)
              &&  qrcode.isDark(row, col + 6) ) {
            lostPoint += 40;
          }
        }
      }

      for (var col = 0; col < moduleCount; col += 1) {
        for (var row = 0; row < moduleCount - 6; row += 1) {
          if (qrcode.isDark(row, col)
              && !qrcode.isDark(row + 1, col)
              &&  qrcode.isDark(row + 2, col)
              &&  qrcode.isDark(row + 3, col)
              &&  qrcode.isDark(row + 4, col)
              && !qrcode.isDark(row + 5, col)
              &&  qrcode.isDark(row + 6, col) ) {
            lostPoint += 40;
          }
        }
      }

      // LEVEL4

      var darkCount = 0;

      for (var col = 0; col < moduleCount; col += 1) {
        for (var row = 0; row < moduleCount; row += 1) {
          if (qrcode.isDark(row, col) ) {
            darkCount += 1;
          }
        }
      }

      var ratio = Math.abs(100 * darkCount / moduleCount / moduleCount - 50) / 5;
      lostPoint += ratio * 10;

      return lostPoint;
    };

    return _this;
  }();

  //---------------------------------------------------------------------
  // QRMath
  //---------------------------------------------------------------------

  var QRMath = function() {

    var EXP_TABLE = new Array(256);
    var LOG_TABLE = new Array(256);

    // initialize tables
    for (var i = 0; i < 8; i += 1) {
      EXP_TABLE[i] = 1 << i;
    }
    for (var i = 8; i < 256; i += 1) {
      EXP_TABLE[i] = EXP_TABLE[i - 4]
        ^ EXP_TABLE[i - 5]
        ^ EXP_TABLE[i - 6]
        ^ EXP_TABLE[i - 8];
    }
    for (var i = 0; i < 255; i += 1) {
      LOG_TABLE[EXP_TABLE[i] ] = i;
    }

    var _this = {};

    _this.glog = function(n) {

      if (n < 1) {
        throw 'glog(' + n + ')';
      }

      return LOG_TABLE[n];
    };

    _this.gexp = function(n) {

      while (n < 0) {
        n += 255;
      }

      while (n >= 256) {
        n -= 255;
      }

      return EXP_TABLE[n];
    };

    return _this;
  }();

  //---------------------------------------------------------------------
  // qrPolynomial
  //---------------------------------------------------------------------

  function qrPolynomial(num, shift) {

    if (typeof num.length == 'undefined') {
      throw num.length + '/' + shift;
    }

    var _num = function() {
      var offset = 0;
      while (offset < num.length && num[offset] == 0) {
        offset += 1;
      }
      var _num = new Array(num.length - offset + shift);
      for (var i = 0; i < num.length - offset; i += 1) {
        _num[i] = num[i + offset];
      }
      return _num;
    }();

    var _this = {};

    _this.getAt = function(index) {
      return _num[index];
    };

    _this.getLength = function() {
      return _num.length;
    };

    _this.multiply = function(e) {

      var num = new Array(_this.getLength() + e.getLength() - 1);

      for (var i = 0; i < _this.getLength(); i += 1) {
        for (var j = 0; j < e.getLength(); j += 1) {
          num[i + j] ^= QRMath.gexp(QRMath.glog(_this.getAt(i) ) + QRMath.glog(e.getAt(j) ) );
        }
      }

      return qrPolynomial(num, 0);
    };

    _this.mod = function(e) {

      if (_this.getLength() - e.getLength() < 0) {
        return _this;
      }

      var ratio = QRMath.glog(_this.getAt(0) ) - QRMath.glog(e.getAt(0) );

      var num = new Array(_this.getLength() );
      for (var i = 0; i < _this.getLength(); i += 1) {
        num[i] = _this.getAt(i);
      }

      for (var i = 0; i < e.getLength(); i += 1) {
        num[i] ^= QRMath.gexp(QRMath.glog(e.getAt(i) ) + ratio);
      }

      // recursive call
      return qrPolynomial(num, 0).mod(e);
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // QRRSBlock
  //---------------------------------------------------------------------

  var QRRSBlock = function() {

    var RS_BLOCK_TABLE = [

      // L
      // M
      // Q
      // H

      // 1
      [1, 26, 19],
      [1, 26, 16],
      [1, 26, 13],
      [1, 26, 9],

      // 2
      [1, 44, 34],
      [1, 44, 28],
      [1, 44, 22],
      [1, 44, 16],

      // 3
      [1, 70, 55],
      [1, 70, 44],
      [2, 35, 17],
      [2, 35, 13],

      // 4
      [1, 100, 80],
      [2, 50, 32],
      [2, 50, 24],
      [4, 25, 9],

      // 5
      [1, 134, 108],
      [2, 67, 43],
      [2, 33, 15, 2, 34, 16],
      [2, 33, 11, 2, 34, 12],

      // 6
      [2, 86, 68],
      [4, 43, 27],
      [4, 43, 19],
      [4, 43, 15],

      // 7
      [2, 98, 78],
      [4, 49, 31],
      [2, 32, 14, 4, 33, 15],
      [4, 39, 13, 1, 40, 14],

      // 8
      [2, 121, 97],
      [2, 60, 38, 2, 61, 39],
      [4, 40, 18, 2, 41, 19],
      [4, 40, 14, 2, 41, 15],

      // 9
      [2, 146, 116],
      [3, 58, 36, 2, 59, 37],
      [4, 36, 16, 4, 37, 17],
      [4, 36, 12, 4, 37, 13],

      // 10
      [2, 86, 68, 2, 87, 69],
      [4, 69, 43, 1, 70, 44],
      [6, 43, 19, 2, 44, 20],
      [6, 43, 15, 2, 44, 16],

      // 11
      [4, 101, 81],
      [1, 80, 50, 4, 81, 51],
      [4, 50, 22, 4, 51, 23],
      [3, 36, 12, 8, 37, 13],

      // 12
      [2, 116, 92, 2, 117, 93],
      [6, 58, 36, 2, 59, 37],
      [4, 46, 20, 6, 47, 21],
      [7, 42, 14, 4, 43, 15],

      // 13
      [4, 133, 107],
      [8, 59, 37, 1, 60, 38],
      [8, 44, 20, 4, 45, 21],
      [12, 33, 11, 4, 34, 12],

      // 14
      [3, 145, 115, 1, 146, 116],
      [4, 64, 40, 5, 65, 41],
      [11, 36, 16, 5, 37, 17],
      [11, 36, 12, 5, 37, 13],

      // 15
      [5, 109, 87, 1, 110, 88],
      [5, 65, 41, 5, 66, 42],
      [5, 54, 24, 7, 55, 25],
      [11, 36, 12, 7, 37, 13],

      // 16
      [5, 122, 98, 1, 123, 99],
      [7, 73, 45, 3, 74, 46],
      [15, 43, 19, 2, 44, 20],
      [3, 45, 15, 13, 46, 16],

      // 17
      [1, 135, 107, 5, 136, 108],
      [10, 74, 46, 1, 75, 47],
      [1, 50, 22, 15, 51, 23],
      [2, 42, 14, 17, 43, 15],

      // 18
      [5, 150, 120, 1, 151, 121],
      [9, 69, 43, 4, 70, 44],
      [17, 50, 22, 1, 51, 23],
      [2, 42, 14, 19, 43, 15],

      // 19
      [3, 141, 113, 4, 142, 114],
      [3, 70, 44, 11, 71, 45],
      [17, 47, 21, 4, 48, 22],
      [9, 39, 13, 16, 40, 14],

      // 20
      [3, 135, 107, 5, 136, 108],
      [3, 67, 41, 13, 68, 42],
      [15, 54, 24, 5, 55, 25],
      [15, 43, 15, 10, 44, 16],

      // 21
      [4, 144, 116, 4, 145, 117],
      [17, 68, 42],
      [17, 50, 22, 6, 51, 23],
      [19, 46, 16, 6, 47, 17],

      // 22
      [2, 139, 111, 7, 140, 112],
      [17, 74, 46],
      [7, 54, 24, 16, 55, 25],
      [34, 37, 13],

      // 23
      [4, 151, 121, 5, 152, 122],
      [4, 75, 47, 14, 76, 48],
      [11, 54, 24, 14, 55, 25],
      [16, 45, 15, 14, 46, 16],

      // 24
      [6, 147, 117, 4, 148, 118],
      [6, 73, 45, 14, 74, 46],
      [11, 54, 24, 16, 55, 25],
      [30, 46, 16, 2, 47, 17],

      // 25
      [8, 132, 106, 4, 133, 107],
      [8, 75, 47, 13, 76, 48],
      [7, 54, 24, 22, 55, 25],
      [22, 45, 15, 13, 46, 16],

      // 26
      [10, 142, 114, 2, 143, 115],
      [19, 74, 46, 4, 75, 47],
      [28, 50, 22, 6, 51, 23],
      [33, 46, 16, 4, 47, 17],

      // 27
      [8, 152, 122, 4, 153, 123],
      [22, 73, 45, 3, 74, 46],
      [8, 53, 23, 26, 54, 24],
      [12, 45, 15, 28, 46, 16],

      // 28
      [3, 147, 117, 10, 148, 118],
      [3, 73, 45, 23, 74, 46],
      [4, 54, 24, 31, 55, 25],
      [11, 45, 15, 31, 46, 16],

      // 29
      [7, 146, 116, 7, 147, 117],
      [21, 73, 45, 7, 74, 46],
      [1, 53, 23, 37, 54, 24],
      [19, 45, 15, 26, 46, 16],

      // 30
      [5, 145, 115, 10, 146, 116],
      [19, 75, 47, 10, 76, 48],
      [15, 54, 24, 25, 55, 25],
      [23, 45, 15, 25, 46, 16],

      // 31
      [13, 145, 115, 3, 146, 116],
      [2, 74, 46, 29, 75, 47],
      [42, 54, 24, 1, 55, 25],
      [23, 45, 15, 28, 46, 16],

      // 32
      [17, 145, 115],
      [10, 74, 46, 23, 75, 47],
      [10, 54, 24, 35, 55, 25],
      [19, 45, 15, 35, 46, 16],

      // 33
      [17, 145, 115, 1, 146, 116],
      [14, 74, 46, 21, 75, 47],
      [29, 54, 24, 19, 55, 25],
      [11, 45, 15, 46, 46, 16],

      // 34
      [13, 145, 115, 6, 146, 116],
      [14, 74, 46, 23, 75, 47],
      [44, 54, 24, 7, 55, 25],
      [59, 46, 16, 1, 47, 17],

      // 35
      [12, 151, 121, 7, 152, 122],
      [12, 75, 47, 26, 76, 48],
      [39, 54, 24, 14, 55, 25],
      [22, 45, 15, 41, 46, 16],

      // 36
      [6, 151, 121, 14, 152, 122],
      [6, 75, 47, 34, 76, 48],
      [46, 54, 24, 10, 55, 25],
      [2, 45, 15, 64, 46, 16],

      // 37
      [17, 152, 122, 4, 153, 123],
      [29, 74, 46, 14, 75, 47],
      [49, 54, 24, 10, 55, 25],
      [24, 45, 15, 46, 46, 16],

      // 38
      [4, 152, 122, 18, 153, 123],
      [13, 74, 46, 32, 75, 47],
      [48, 54, 24, 14, 55, 25],
      [42, 45, 15, 32, 46, 16],

      // 39
      [20, 147, 117, 4, 148, 118],
      [40, 75, 47, 7, 76, 48],
      [43, 54, 24, 22, 55, 25],
      [10, 45, 15, 67, 46, 16],

      // 40
      [19, 148, 118, 6, 149, 119],
      [18, 75, 47, 31, 76, 48],
      [34, 54, 24, 34, 55, 25],
      [20, 45, 15, 61, 46, 16]
    ];

    var qrRSBlock = function(totalCount, dataCount) {
      var _this = {};
      _this.totalCount = totalCount;
      _this.dataCount = dataCount;
      return _this;
    };

    var _this = {};

    var getRsBlockTable = function(typeNumber, errorCorrectionLevel) {

      switch(errorCorrectionLevel) {
      case QRErrorCorrectionLevel.L :
        return RS_BLOCK_TABLE[(typeNumber - 1) * 4 + 0];
      case QRErrorCorrectionLevel.M :
        return RS_BLOCK_TABLE[(typeNumber - 1) * 4 + 1];
      case QRErrorCorrectionLevel.Q :
        return RS_BLOCK_TABLE[(typeNumber - 1) * 4 + 2];
      case QRErrorCorrectionLevel.H :
        return RS_BLOCK_TABLE[(typeNumber - 1) * 4 + 3];
      default :
        return undefined;
      }
    };

    _this.getRSBlocks = function(typeNumber, errorCorrectionLevel) {

      var rsBlock = getRsBlockTable(typeNumber, errorCorrectionLevel);

      if (typeof rsBlock == 'undefined') {
        throw 'bad rs block @ typeNumber:' + typeNumber +
            '/errorCorrectionLevel:' + errorCorrectionLevel;
      }

      var length = rsBlock.length / 3;

      var list = [];

      for (var i = 0; i < length; i += 1) {

        var count = rsBlock[i * 3 + 0];
        var totalCount = rsBlock[i * 3 + 1];
        var dataCount = rsBlock[i * 3 + 2];

        for (var j = 0; j < count; j += 1) {
          list.push(qrRSBlock(totalCount, dataCount) );
        }
      }

      return list;
    };

    return _this;
  }();

  //---------------------------------------------------------------------
  // qrBitBuffer
  //---------------------------------------------------------------------

  var qrBitBuffer = function() {

    var _buffer = [];
    var _length = 0;

    var _this = {};

    _this.getBuffer = function() {
      return _buffer;
    };

    _this.getAt = function(index) {
      var bufIndex = Math.floor(index / 8);
      return ( (_buffer[bufIndex] >>> (7 - index % 8) ) & 1) == 1;
    };

    _this.put = function(num, length) {
      for (var i = 0; i < length; i += 1) {
        _this.putBit( ( (num >>> (length - i - 1) ) & 1) == 1);
      }
    };

    _this.getLengthInBits = function() {
      return _length;
    };

    _this.putBit = function(bit) {

      var bufIndex = Math.floor(_length / 8);
      if (_buffer.length <= bufIndex) {
        _buffer.push(0);
      }

      if (bit) {
        _buffer[bufIndex] |= (0x80 >>> (_length % 8) );
      }

      _length += 1;
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // qrNumber
  //---------------------------------------------------------------------

  var qrNumber = function(data) {

    var _mode = QRMode.MODE_NUMBER;
    var _data = data;

    var _this = {};

    _this.getMode = function() {
      return _mode;
    };

    _this.getLength = function(buffer) {
      return _data.length;
    };

    _this.write = function(buffer) {

      var data = _data;

      var i = 0;

      while (i + 2 < data.length) {
        buffer.put(strToNum(data.substring(i, i + 3) ), 10);
        i += 3;
      }

      if (i < data.length) {
        if (data.length - i == 1) {
          buffer.put(strToNum(data.substring(i, i + 1) ), 4);
        } else if (data.length - i == 2) {
          buffer.put(strToNum(data.substring(i, i + 2) ), 7);
        }
      }
    };

    var strToNum = function(s) {
      var num = 0;
      for (var i = 0; i < s.length; i += 1) {
        num = num * 10 + chatToNum(s.charAt(i) );
      }
      return num;
    };

    var chatToNum = function(c) {
      if ('0' <= c && c <= '9') {
        return c.charCodeAt(0) - '0'.charCodeAt(0);
      }
      throw 'illegal char :' + c;
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // qrAlphaNum
  //---------------------------------------------------------------------

  var qrAlphaNum = function(data) {

    var _mode = QRMode.MODE_ALPHA_NUM;
    var _data = data;

    var _this = {};

    _this.getMode = function() {
      return _mode;
    };

    _this.getLength = function(buffer) {
      return _data.length;
    };

    _this.write = function(buffer) {

      var s = _data;

      var i = 0;

      while (i + 1 < s.length) {
        buffer.put(
          getCode(s.charAt(i) ) * 45 +
          getCode(s.charAt(i + 1) ), 11);
        i += 2;
      }

      if (i < s.length) {
        buffer.put(getCode(s.charAt(i) ), 6);
      }
    };

    var getCode = function(c) {

      if ('0' <= c && c <= '9') {
        return c.charCodeAt(0) - '0'.charCodeAt(0);
      } else if ('A' <= c && c <= 'Z') {
        return c.charCodeAt(0) - 'A'.charCodeAt(0) + 10;
      } else {
        switch (c) {
        case ' ' : return 36;
        case '$' : return 37;
        case '%' : return 38;
        case '*' : return 39;
        case '+' : return 40;
        case '-' : return 41;
        case '.' : return 42;
        case '/' : return 43;
        case ':' : return 44;
        default :
          throw 'illegal char :' + c;
        }
      }
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // qr8BitByte
  //---------------------------------------------------------------------

  var qr8BitByte = function(data) {

    var _mode = QRMode.MODE_8BIT_BYTE;
    var _data = data;
    var _bytes = qrcode.stringToBytes(data);

    var _this = {};

    _this.getMode = function() {
      return _mode;
    };

    _this.getLength = function(buffer) {
      return _bytes.length;
    };

    _this.write = function(buffer) {
      for (var i = 0; i < _bytes.length; i += 1) {
        buffer.put(_bytes[i], 8);
      }
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // qrKanji
  //---------------------------------------------------------------------

  var qrKanji = function(data) {

    var _mode = QRMode.MODE_KANJI;
    var _data = data;

    var stringToBytes = qrcode.stringToBytesFuncs['SJIS'];
    if (!stringToBytes) {
      throw 'sjis not supported.';
    }
    !function(c, code) {
      // self test for sjis support.
      var test = stringToBytes(c);
      if (test.length != 2 || ( (test[0] << 8) | test[1]) != code) {
        throw 'sjis not supported.';
      }
    }('\u53cb', 0x9746);

    var _bytes = stringToBytes(data);

    var _this = {};

    _this.getMode = function() {
      return _mode;
    };

    _this.getLength = function(buffer) {
      return ~~(_bytes.length / 2);
    };

    _this.write = function(buffer) {

      var data = _bytes;

      var i = 0;

      while (i + 1 < data.length) {

        var c = ( (0xff & data[i]) << 8) | (0xff & data[i + 1]);

        if (0x8140 <= c && c <= 0x9FFC) {
          c -= 0x8140;
        } else if (0xE040 <= c && c <= 0xEBBF) {
          c -= 0xC140;
        } else {
          throw 'illegal char at ' + (i + 1) + '/' + c;
        }

        c = ( (c >>> 8) & 0xff) * 0xC0 + (c & 0xff);

        buffer.put(c, 13);

        i += 2;
      }

      if (i < data.length) {
        throw 'illegal char at ' + (i + 1);
      }
    };

    return _this;
  };

  //=====================================================================
  // GIF Support etc.
  //

  //---------------------------------------------------------------------
  // byteArrayOutputStream
  //---------------------------------------------------------------------

  var byteArrayOutputStream = function() {

    var _bytes = [];

    var _this = {};

    _this.writeByte = function(b) {
      _bytes.push(b & 0xff);
    };

    _this.writeShort = function(i) {
      _this.writeByte(i);
      _this.writeByte(i >>> 8);
    };

    _this.writeBytes = function(b, off, len) {
      off = off || 0;
      len = len || b.length;
      for (var i = 0; i < len; i += 1) {
        _this.writeByte(b[i + off]);
      }
    };

    _this.writeString = function(s) {
      for (var i = 0; i < s.length; i += 1) {
        _this.writeByte(s.charCodeAt(i) );
      }
    };

    _this.toByteArray = function() {
      return _bytes;
    };

    _this.toString = function() {
      var s = '';
      s += '[';
      for (var i = 0; i < _bytes.length; i += 1) {
        if (i > 0) {
          s += ',';
        }
        s += _bytes[i];
      }
      s += ']';
      return s;
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // base64EncodeOutputStream
  //---------------------------------------------------------------------

  var base64EncodeOutputStream = function() {

    var _buffer = 0;
    var _buflen = 0;
    var _length = 0;
    var _base64 = '';

    var _this = {};

    var writeEncoded = function(b) {
      _base64 += String.fromCharCode(encode(b & 0x3f) );
    };

    var encode = function(n) {
      if (n < 0) {
        // error.
      } else if (n < 26) {
        return 0x41 + n;
      } else if (n < 52) {
        return 0x61 + (n - 26);
      } else if (n < 62) {
        return 0x30 + (n - 52);
      } else if (n == 62) {
        return 0x2b;
      } else if (n == 63) {
        return 0x2f;
      }
      throw 'n:' + n;
    };

    _this.writeByte = function(n) {

      _buffer = (_buffer << 8) | (n & 0xff);
      _buflen += 8;
      _length += 1;

      while (_buflen >= 6) {
        writeEncoded(_buffer >>> (_buflen - 6) );
        _buflen -= 6;
      }
    };

    _this.flush = function() {

      if (_buflen > 0) {
        writeEncoded(_buffer << (6 - _buflen) );
        _buffer = 0;
        _buflen = 0;
      }

      if (_length % 3 != 0) {
        // padding
        var padlen = 3 - _length % 3;
        for (var i = 0; i < padlen; i += 1) {
          _base64 += '=';
        }
      }
    };

    _this.toString = function() {
      return _base64;
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // base64DecodeInputStream
  //---------------------------------------------------------------------

  var base64DecodeInputStream = function(str) {

    var _str = str;
    var _pos = 0;
    var _buffer = 0;
    var _buflen = 0;

    var _this = {};

    _this.read = function() {

      while (_buflen < 8) {

        if (_pos >= _str.length) {
          if (_buflen == 0) {
            return -1;
          }
          throw 'unexpected end of file./' + _buflen;
        }

        var c = _str.charAt(_pos);
        _pos += 1;

        if (c == '=') {
          _buflen = 0;
          return -1;
        } else if (c.match(/^\s$/) ) {
          // ignore if whitespace.
          continue;
        }

        _buffer = (_buffer << 6) | decode(c.charCodeAt(0) );
        _buflen += 6;
      }

      var n = (_buffer >>> (_buflen - 8) ) & 0xff;
      _buflen -= 8;
      return n;
    };

    var decode = function(c) {
      if (0x41 <= c && c <= 0x5a) {
        return c - 0x41;
      } else if (0x61 <= c && c <= 0x7a) {
        return c - 0x61 + 26;
      } else if (0x30 <= c && c <= 0x39) {
        return c - 0x30 + 52;
      } else if (c == 0x2b) {
        return 62;
      } else if (c == 0x2f) {
        return 63;
      } else {
        throw 'c:' + c;
      }
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // gifImage (B/W)
  //---------------------------------------------------------------------

  var gifImage = function(width, height) {

    var _width = width;
    var _height = height;
    var _data = new Array(width * height);

    var _this = {};

    _this.setPixel = function(x, y, pixel) {
      _data[y * _width + x] = pixel;
    };

    _this.write = function(out) {

      //---------------------------------
      // GIF Signature

      out.writeString('GIF87a');

      //---------------------------------
      // Screen Descriptor

      out.writeShort(_width);
      out.writeShort(_height);

      out.writeByte(0x80); // 2bit
      out.writeByte(0);
      out.writeByte(0);

      //---------------------------------
      // Global Color Map

      // black
      out.writeByte(0x00);
      out.writeByte(0x00);
      out.writeByte(0x00);

      // white
      out.writeByte(0xff);
      out.writeByte(0xff);
      out.writeByte(0xff);

      //---------------------------------
      // Image Descriptor

      out.writeString(',');
      out.writeShort(0);
      out.writeShort(0);
      out.writeShort(_width);
      out.writeShort(_height);
      out.writeByte(0);

      //---------------------------------
      // Local Color Map

      //---------------------------------
      // Raster Data

      var lzwMinCodeSize = 2;
      var raster = getLZWRaster(lzwMinCodeSize);

      out.writeByte(lzwMinCodeSize);

      var offset = 0;

      while (raster.length - offset > 255) {
        out.writeByte(255);
        out.writeBytes(raster, offset, 255);
        offset += 255;
      }

      out.writeByte(raster.length - offset);
      out.writeBytes(raster, offset, raster.length - offset);
      out.writeByte(0x00);

      //---------------------------------
      // GIF Terminator
      out.writeString(';');
    };

    var bitOutputStream = function(out) {

      var _out = out;
      var _bitLength = 0;
      var _bitBuffer = 0;

      var _this = {};

      _this.write = function(data, length) {

        if ( (data >>> length) != 0) {
          throw 'length over';
        }

        while (_bitLength + length >= 8) {
          _out.writeByte(0xff & ( (data << _bitLength) | _bitBuffer) );
          length -= (8 - _bitLength);
          data >>>= (8 - _bitLength);
          _bitBuffer = 0;
          _bitLength = 0;
        }

        _bitBuffer = (data << _bitLength) | _bitBuffer;
        _bitLength = _bitLength + length;
      };

      _this.flush = function() {
        if (_bitLength > 0) {
          _out.writeByte(_bitBuffer);
        }
      };

      return _this;
    };

    var getLZWRaster = function(lzwMinCodeSize) {

      var clearCode = 1 << lzwMinCodeSize;
      var endCode = (1 << lzwMinCodeSize) + 1;
      var bitLength = lzwMinCodeSize + 1;

      // Setup LZWTable
      var table = lzwTable();

      for (var i = 0; i < clearCode; i += 1) {
        table.add(String.fromCharCode(i) );
      }
      table.add(String.fromCharCode(clearCode) );
      table.add(String.fromCharCode(endCode) );

      var byteOut = byteArrayOutputStream();
      var bitOut = bitOutputStream(byteOut);

      // clear code
      bitOut.write(clearCode, bitLength);

      var dataIndex = 0;

      var s = String.fromCharCode(_data[dataIndex]);
      dataIndex += 1;

      while (dataIndex < _data.length) {

        var c = String.fromCharCode(_data[dataIndex]);
        dataIndex += 1;

        if (table.contains(s + c) ) {

          s = s + c;

        } else {

          bitOut.write(table.indexOf(s), bitLength);

          if (table.size() < 0xfff) {

            if (table.size() == (1 << bitLength) ) {
              bitLength += 1;
            }

            table.add(s + c);
          }

          s = c;
        }
      }

      bitOut.write(table.indexOf(s), bitLength);

      // end code
      bitOut.write(endCode, bitLength);

      bitOut.flush();

      return byteOut.toByteArray();
    };

    var lzwTable = function() {

      var _map = {};
      var _size = 0;

      var _this = {};

      _this.add = function(key) {
        if (_this.contains(key) ) {
          throw 'dup key:' + key;
        }
        _map[key] = _size;
        _size += 1;
      };

      _this.size = function() {
        return _size;
      };

      _this.indexOf = function(key) {
        return _map[key];
      };

      _this.contains = function(key) {
        return typeof _map[key] != 'undefined';
      };

      return _this;
    };

    return _this;
  };

  var createDataURL = function(width, height, getPixel) {
    var gif = gifImage(width, height);
    for (var y = 0; y < height; y += 1) {
      for (var x = 0; x < width; x += 1) {
        gif.setPixel(x, y, getPixel(x, y) );
      }
    }

    var b = byteArrayOutputStream();
    gif.write(b);

    var base64 = base64EncodeOutputStream();
    var bytes = b.toByteArray();
    for (var i = 0; i < bytes.length; i += 1) {
      base64.writeByte(bytes[i]);
    }
    base64.flush();

    return 'data:image/gif;base64,' + base64;
  };

  //---------------------------------------------------------------------
  // returns qrcode function.

  return qrcode;
}();

// multibyte support
!function() {

  qrcode.stringToBytesFuncs['UTF-8'] = function(s) {
    // http://stackoverflow.com/questions/18729405/how-to-convert-utf8-string-to-byte-array
    function toUTF8Array(str) {
      var utf8 = [];
      for (var i=0; i < str.length; i++) {
        var charcode = str.charCodeAt(i);
        if (charcode < 0x80) utf8.push(charcode);
        else if (charcode < 0x800) {
          utf8.push(0xc0 | (charcode >> 6),
              0x80 | (charcode & 0x3f));
        }
        else if (charcode < 0xd800 || charcode >= 0xe000) {
          utf8.push(0xe0 | (charcode >> 12),
              0x80 | ((charcode>>6) & 0x3f),
              0x80 | (charcode & 0x3f));
        }
        // surrogate pair
        else {
          i++;
          // UTF-16 encodes 0x10000-0x10FFFF by
          // subtracting 0x10000 and splitting the
          // 20 bits of 0x0-0xFFFFF into two halves
          charcode = 0x10000 + (((charcode & 0x3ff)<<10)
            | (str.charCodeAt(i) & 0x3ff));
          utf8.push(0xf0 | (charcode >>18),
              0x80 | ((charcode>>12) & 0x3f),
              0x80 | ((charcode>>6) & 0x3f),
              0x80 | (charcode & 0x3f));
        }
      }
      return utf8;
    }
    return toUTF8Array(s);
  };

}();

(function (factory) {
  if (typeof define === 'function' && define.amd) {
      define([], factory);
  } else if (typeof exports === 'object') {
      module.exports = factory();
  }
}(function () {
    return qrcode;
}));

/**
 * Minified by jsDelivr using Terser v5.39.0.
 * Original file: /npm/jsqr@1.4.0/dist/jsQR.js
 *
 * Do NOT use SRI with dynamically generated files! More information: https://www.jsdelivr.com/using-sri-with-dynamic-files
 */
!function(o,e){"object"==typeof exports&&"object"==typeof module?module.exports=e():"function"==typeof define&&define.amd?define([],e):"object"==typeof exports?exports.jsQR=e():o.jsQR=e()}("undefined"!=typeof self?self:this,(function(){return function(o){var e={};function r(t){if(e[t])return e[t].exports;var c=e[t]={i:t,l:!1,exports:{}};return o[t].call(c.exports,c,c.exports,r),c.l=!0,c.exports}return r.m=o,r.c=e,r.d=function(o,e,t){r.o(o,e)||Object.defineProperty(o,e,{configurable:!1,enumerable:!0,get:t})},r.n=function(o){var e=o&&o.__esModule?function(){return o.default}:function(){return o};return r.d(e,"a",e),e},r.o=function(o,e){return Object.prototype.hasOwnProperty.call(o,e)},r.p="",r(r.s=3)}([function(o,e,r){"use strict";Object.defineProperty(e,"__esModule",{value:!0});var t=function(){function o(o,e){this.width=e,this.height=o.length/e,this.data=o}return o.createEmpty=function(e,r){return new o(new Uint8ClampedArray(e*r),e)},o.prototype.get=function(o,e){return!(o<0||o>=this.width||e<0||e>=this.height)&&!!this.data[e*this.width+o]},o.prototype.set=function(o,e,r){this.data[e*this.width+o]=r?1:0},o.prototype.setRegion=function(o,e,r,t,c){for(var s=e;s<e+t;s++)for(var a=o;a<o+r;a++)this.set(a,s,!!c)},o}();e.BitMatrix=t},function(o,e,r){"use strict";Object.defineProperty(e,"__esModule",{value:!0});var t=r(2);e.addOrSubtractGF=function(o,e){return o^e};var c=function(){function o(o,e,r){this.primitive=o,this.size=e,this.generatorBase=r,this.expTable=new Array(this.size),this.logTable=new Array(this.size);for(var c=1,s=0;s<this.size;s++)this.expTable[s]=c,(c*=2)>=this.size&&(c=(c^this.primitive)&this.size-1);for(s=0;s<this.size-1;s++)this.logTable[this.expTable[s]]=s;this.zero=new t.default(this,Uint8ClampedArray.from([0])),this.one=new t.default(this,Uint8ClampedArray.from([1]))}return o.prototype.multiply=function(o,e){return 0===o||0===e?0:this.expTable[(this.logTable[o]+this.logTable[e])%(this.size-1)]},o.prototype.inverse=function(o){if(0===o)throw new Error("Can't invert 0");return this.expTable[this.size-this.logTable[o]-1]},o.prototype.buildMonomial=function(o,e){if(o<0)throw new Error("Invalid monomial degree less than 0");if(0===e)return this.zero;var r=new Uint8ClampedArray(o+1);return r[0]=e,new t.default(this,r)},o.prototype.log=function(o){if(0===o)throw new Error("Can't take log(0)");return this.logTable[o]},o.prototype.exp=function(o){return this.expTable[o]},o}();e.default=c},function(o,e,r){"use strict";Object.defineProperty(e,"__esModule",{value:!0});var t=r(1),c=function(){function o(o,e){if(0===e.length)throw new Error("No coefficients.");this.field=o;var r=e.length;if(r>1&&0===e[0]){for(var t=1;t<r&&0===e[t];)t++;if(t===r)this.coefficients=o.zero.coefficients;else{this.coefficients=new Uint8ClampedArray(r-t);for(var c=0;c<this.coefficients.length;c++)this.coefficients[c]=e[t+c]}}else this.coefficients=e}return o.prototype.degree=function(){return this.coefficients.length-1},o.prototype.isZero=function(){return 0===this.coefficients[0]},o.prototype.getCoefficient=function(o){return this.coefficients[this.coefficients.length-1-o]},o.prototype.addOrSubtract=function(e){var r;if(this.isZero())return e;if(e.isZero())return this;var c=this.coefficients,s=e.coefficients;c.length>s.length&&(c=(r=[s,c])[0],s=r[1]);for(var a=new Uint8ClampedArray(s.length),n=s.length-c.length,d=0;d<n;d++)a[d]=s[d];for(d=n;d<s.length;d++)a[d]=t.addOrSubtractGF(c[d-n],s[d]);return new o(this.field,a)},o.prototype.multiply=function(e){if(0===e)return this.field.zero;if(1===e)return this;for(var r=this.coefficients.length,t=new Uint8ClampedArray(r),c=0;c<r;c++)t[c]=this.field.multiply(this.coefficients[c],e);return new o(this.field,t)},o.prototype.multiplyPoly=function(e){if(this.isZero()||e.isZero())return this.field.zero;for(var r=this.coefficients,c=r.length,s=e.coefficients,a=s.length,n=new Uint8ClampedArray(c+a-1),d=0;d<c;d++)for(var l=r[d],i=0;i<a;i++)n[d+i]=t.addOrSubtractGF(n[d+i],this.field.multiply(l,s[i]));return new o(this.field,n)},o.prototype.multiplyByMonomial=function(e,r){if(e<0)throw new Error("Invalid degree less than 0");if(0===r)return this.field.zero;for(var t=this.coefficients.length,c=new Uint8ClampedArray(t+e),s=0;s<t;s++)c[s]=this.field.multiply(this.coefficients[s],r);return new o(this.field,c)},o.prototype.evaluateAt=function(o){var e=0;if(0===o)return this.getCoefficient(0);var r=this.coefficients.length;if(1===o)return this.coefficients.forEach((function(o){e=t.addOrSubtractGF(e,o)})),e;e=this.coefficients[0];for(var c=1;c<r;c++)e=t.addOrSubtractGF(this.field.multiply(o,e),this.coefficients[c]);return e},o}();e.default=c},function(o,e,r){"use strict";Object.defineProperty(e,"__esModule",{value:!0});var t=r(4),c=r(5),s=r(11),a=r(12);function n(o){var e=a.locate(o);if(!e)return null;for(var r=0,t=e;r<t.length;r++){var n=t[r],d=s.extract(o,n),l=c.decode(d.matrix);if(l)return{binaryData:l.bytes,data:l.text,chunks:l.chunks,version:l.version,location:{topRightCorner:d.mappingFunction(n.dimension,0),topLeftCorner:d.mappingFunction(0,0),bottomRightCorner:d.mappingFunction(n.dimension,n.dimension),bottomLeftCorner:d.mappingFunction(0,n.dimension),topRightFinderPattern:n.topRight,topLeftFinderPattern:n.topLeft,bottomLeftFinderPattern:n.bottomLeft,bottomRightAlignmentPattern:n.alignmentPattern}}}return null}var d={inversionAttempts:"attemptBoth"};function l(o,e,r,c){void 0===c&&(c={});var s=d;Object.keys(s||{}).forEach((function(o){s[o]=c[o]||s[o]}));var a="attemptBoth"===s.inversionAttempts||"invertFirst"===s.inversionAttempts,l="onlyInvert"===s.inversionAttempts||"invertFirst"===s.inversionAttempts,i=t.binarize(o,e,r,a),B=i.binarized,k=i.inverted,u=n(l?k:B);return u||"attemptBoth"!==s.inversionAttempts&&"invertFirst"!==s.inversionAttempts||(u=n(l?B:k)),u}l.default=l,e.default=l},function(o,e,r){"use strict";Object.defineProperty(e,"__esModule",{value:!0});var t=r(0);function c(o,e,r){return o<e?e:o>r?r:o}var s=function(){function o(o,e){this.width=o,this.data=new Uint8ClampedArray(o*e)}return o.prototype.get=function(o,e){return this.data[e*this.width+o]},o.prototype.set=function(o,e,r){this.data[e*this.width+o]=r},o}();e.binarize=function(o,e,r,a){if(o.length!==e*r*4)throw new Error("Malformed data passed to binarizer.");for(var n=new s(e,r),d=0;d<e;d++)for(var l=0;l<r;l++){var i=o[4*(l*e+d)+0],B=o[4*(l*e+d)+1],k=o[4*(l*e+d)+2];n.set(d,l,.2126*i+.7152*B+.0722*k)}for(var u=Math.ceil(e/8),C=Math.ceil(r/8),m=new s(u,C),f=0;f<C;f++)for(var w=0;w<u;w++){var P=0,v=1/0,h=0;for(l=0;l<8;l++)for(d=0;d<8;d++){var y=n.get(8*w+d,8*f+l);P+=y,v=Math.min(v,y),h=Math.max(h,y)}var p=P/Math.pow(8,2);if(h-v<=24&&(p=v/2,f>0&&w>0)){var b=(m.get(w,f-1)+2*m.get(w-1,f)+m.get(w-1,f-1))/4;v<b&&(p=b)}m.set(w,f,p)}var g=t.BitMatrix.createEmpty(e,r),x=null;for(a&&(x=t.BitMatrix.createEmpty(e,r)),f=0;f<C;f++)for(w=0;w<u;w++){for(var M=c(w,2,u-3),L=c(f,2,C-3),N=(P=0,-2);N<=2;N++)for(var I=-2;I<=2;I++)P+=m.get(M+N,L+I);var O=P/25;for(N=0;N<8;N++)for(I=0;I<8;I++){d=8*w+N,l=8*f+I;var z=n.get(d,l);g.set(d,l,z<=O),a&&x.set(d,l,!(z<=O))}}return a?{binarized:g,inverted:x}:{binarized:g}}},function(o,e,r){"use strict";Object.defineProperty(e,"__esModule",{value:!0});var t=r(0),c=r(6),s=r(9),a=r(10);function n(o,e){for(var r=o^e,t=0;r;)t++,r&=r-1;return t}function d(o,e){return e<<1|o}var l=[{bits:21522,formatInfo:{errorCorrectionLevel:1,dataMask:0}},{bits:20773,formatInfo:{errorCorrectionLevel:1,dataMask:1}},{bits:24188,formatInfo:{errorCorrectionLevel:1,dataMask:2}},{bits:23371,formatInfo:{errorCorrectionLevel:1,dataMask:3}},{bits:17913,formatInfo:{errorCorrectionLevel:1,dataMask:4}},{bits:16590,formatInfo:{errorCorrectionLevel:1,dataMask:5}},{bits:20375,formatInfo:{errorCorrectionLevel:1,dataMask:6}},{bits:19104,formatInfo:{errorCorrectionLevel:1,dataMask:7}},{bits:30660,formatInfo:{errorCorrectionLevel:0,dataMask:0}},{bits:29427,formatInfo:{errorCorrectionLevel:0,dataMask:1}},{bits:32170,formatInfo:{errorCorrectionLevel:0,dataMask:2}},{bits:30877,formatInfo:{errorCorrectionLevel:0,dataMask:3}},{bits:26159,formatInfo:{errorCorrectionLevel:0,dataMask:4}},{bits:25368,formatInfo:{errorCorrectionLevel:0,dataMask:5}},{bits:27713,formatInfo:{errorCorrectionLevel:0,dataMask:6}},{bits:26998,formatInfo:{errorCorrectionLevel:0,dataMask:7}},{bits:5769,formatInfo:{errorCorrectionLevel:3,dataMask:0}},{bits:5054,formatInfo:{errorCorrectionLevel:3,dataMask:1}},{bits:7399,formatInfo:{errorCorrectionLevel:3,dataMask:2}},{bits:6608,formatInfo:{errorCorrectionLevel:3,dataMask:3}},{bits:1890,formatInfo:{errorCorrectionLevel:3,dataMask:4}},{bits:597,formatInfo:{errorCorrectionLevel:3,dataMask:5}},{bits:3340,formatInfo:{errorCorrectionLevel:3,dataMask:6}},{bits:2107,formatInfo:{errorCorrectionLevel:3,dataMask:7}},{bits:13663,formatInfo:{errorCorrectionLevel:2,dataMask:0}},{bits:12392,formatInfo:{errorCorrectionLevel:2,dataMask:1}},{bits:16177,formatInfo:{errorCorrectionLevel:2,dataMask:2}},{bits:14854,formatInfo:{errorCorrectionLevel:2,dataMask:3}},{bits:9396,formatInfo:{errorCorrectionLevel:2,dataMask:4}},{bits:8579,formatInfo:{errorCorrectionLevel:2,dataMask:5}},{bits:11994,formatInfo:{errorCorrectionLevel:2,dataMask:6}},{bits:11245,formatInfo:{errorCorrectionLevel:2,dataMask:7}}],i=[function(o){return(o.y+o.x)%2==0},function(o){return o.y%2==0},function(o){return o.x%3==0},function(o){return(o.y+o.x)%3==0},function(o){return(Math.floor(o.y/2)+Math.floor(o.x/3))%2==0},function(o){return o.x*o.y%2+o.x*o.y%3==0},function(o){return(o.y*o.x%2+o.y*o.x%3)%2==0},function(o){return((o.y+o.x)%2+o.y*o.x%3)%2==0}];function B(o,e,r){for(var c=i[r.dataMask],s=o.height,a=function(o){var e=17+4*o.versionNumber,r=t.BitMatrix.createEmpty(e,e);r.setRegion(0,0,9,9,!0),r.setRegion(e-8,0,8,9,!0),r.setRegion(0,e-8,9,8,!0);for(var c=0,s=o.alignmentPatternCenters;c<s.length;c++)for(var a=s[c],n=0,d=o.alignmentPatternCenters;n<d.length;n++){var l=d[n];6===a&&6===l||6===a&&l===e-7||a===e-7&&6===l||r.setRegion(a-2,l-2,5,5,!0)}return r.setRegion(6,9,1,e-17,!0),r.setRegion(9,6,e-17,1,!0),o.versionNumber>6&&(r.setRegion(e-11,0,3,6,!0),r.setRegion(0,e-11,6,3,!0)),r}(e),n=[],l=0,B=0,k=!0,u=s-1;u>0;u-=2){6===u&&u--;for(var C=0;C<s;C++)for(var m=k?s-1-C:C,f=0;f<2;f++){var w=u-f;if(!a.get(w,m)){B++;var P=o.get(w,m);c({y:m,x:w})&&(P=!P),l=d(P,l),8===B&&(n.push(l),B=0,l=0)}}k=!k}return n}function k(o){var e=function(o){var e=o.height,r=Math.floor((e-17)/4);if(r<=6)return a.VERSIONS[r-1];for(var t=0,c=5;c>=0;c--)for(var s=e-9;s>=e-11;s--)t=d(o.get(s,c),t);var l=0;for(s=5;s>=0;s--)for(c=e-9;c>=e-11;c--)l=d(o.get(s,c),l);for(var i,B=1/0,k=0,u=a.VERSIONS;k<u.length;k++){var C=u[k];if(C.infoBits===t||C.infoBits===l)return C;var m=n(t,C.infoBits);m<B&&(i=C,B=m),(m=n(l,C.infoBits))<B&&(i=C,B=m)}return B<=3?i:void 0}(o);if(!e)return null;var r=function(o){for(var e=0,r=0;r<=8;r++)6!==r&&(e=d(o.get(r,8),e));for(var t=7;t>=0;t--)6!==t&&(e=d(o.get(8,t),e));var c=o.height,s=0;for(t=c-1;t>=c-7;t--)s=d(o.get(8,t),s);for(r=c-8;r<c;r++)s=d(o.get(r,8),s);for(var a=1/0,i=null,B=0,k=l;B<k.length;B++){var u=k[B],C=u.bits,m=u.formatInfo;if(C===e||C===s)return m;var f=n(e,C);f<a&&(i=m,a=f),e!==s&&(f=n(s,C))<a&&(i=m,a=f)}return a<=3?i:null}(o);if(!r)return null;var t=function(o,e,r){var t=e.errorCorrectionLevels[r],c=[],s=0;if(t.ecBlocks.forEach((function(o){for(var e=0;e<o.numBlocks;e++)c.push({numDataCodewords:o.dataCodewordsPerBlock,codewords:[]}),s+=o.dataCodewordsPerBlock+t.ecCodewordsPerBlock})),o.length<s)return null;o=o.slice(0,s);for(var a=t.ecBlocks[0].dataCodewordsPerBlock,n=0;n<a;n++)for(var d=0,l=c;d<l.length;d++)l[d].codewords.push(o.shift());if(t.ecBlocks.length>1){var i=t.ecBlocks[0].numBlocks,B=t.ecBlocks[1].numBlocks;for(n=0;n<B;n++)c[i+n].codewords.push(o.shift())}for(;o.length>0;)for(var k=0,u=c;k<u.length;k++)u[k].codewords.push(o.shift());return c}(B(o,e,r),e,r.errorCorrectionLevel);if(!t)return null;for(var i=t.reduce((function(o,e){return o+e.numDataCodewords}),0),k=new Uint8ClampedArray(i),u=0,C=0,m=t;C<m.length;C++){var f=m[C],w=s.decode(f.codewords,f.codewords.length-f.numDataCodewords);if(!w)return null;for(var P=0;P<f.numDataCodewords;P++)k[u++]=w[P]}try{return c.decode(k,e.versionNumber)}catch(o){return null}}e.decode=function(o){if(null==o)return null;var e=k(o);if(e)return e;for(var r=0;r<o.width;r++)for(var t=r+1;t<o.height;t++)o.get(r,t)!==o.get(t,r)&&(o.set(r,t,!o.get(r,t)),o.set(t,r,!o.get(t,r)));return k(o)}},function(o,e,r){"use strict";Object.defineProperty(e,"__esModule",{value:!0});var t,c,s=r(7),a=r(8);function n(o,e){for(var r=[],t="",c=[10,12,14][e],s=o.readBits(c);s>=3;){if((l=o.readBits(10))>=1e3)throw new Error("Invalid numeric value above 999");var a=Math.floor(l/100),n=Math.floor(l/10)%10,d=l%10;r.push(48+a,48+n,48+d),t+=a.toString()+n.toString()+d.toString(),s-=3}if(2===s){if((l=o.readBits(7))>=100)throw new Error("Invalid numeric value above 99");a=Math.floor(l/10),n=l%10;r.push(48+a,48+n),t+=a.toString()+n.toString()}else if(1===s){var l;if((l=o.readBits(4))>=10)throw new Error("Invalid numeric value above 9");r.push(48+l),t+=l.toString()}return{bytes:r,text:t}}!function(o){o.Numeric="numeric",o.Alphanumeric="alphanumeric",o.Byte="byte",o.Kanji="kanji",o.ECI="eci"}(t=e.Mode||(e.Mode={})),function(o){o[o.Terminator=0]="Terminator",o[o.Numeric=1]="Numeric",o[o.Alphanumeric=2]="Alphanumeric",o[o.Byte=4]="Byte",o[o.Kanji=8]="Kanji",o[o.ECI=7]="ECI"}(c||(c={}));var d=["0","1","2","3","4","5","6","7","8","9","A","B","C","D","E","F","G","H","I","J","K","L","M","N","O","P","Q","R","S","T","U","V","W","X","Y","Z"," ","$","%","*","+","-",".","/",":"];function l(o,e){for(var r=[],t="",c=[9,11,13][e],s=o.readBits(c);s>=2;){var a=o.readBits(11),n=Math.floor(a/45),l=a%45;r.push(d[n].charCodeAt(0),d[l].charCodeAt(0)),t+=d[n]+d[l],s-=2}if(1===s){n=o.readBits(6);r.push(d[n].charCodeAt(0)),t+=d[n]}return{bytes:r,text:t}}function i(o,e){for(var r=[],t="",c=[8,16,16][e],s=o.readBits(c),a=0;a<s;a++){var n=o.readBits(8);r.push(n)}try{t+=decodeURIComponent(r.map((function(o){return"%"+("0"+o.toString(16)).substr(-2)})).join(""))}catch(o){}return{bytes:r,text:t}}function B(o,e){for(var r=[],t="",c=[8,10,12][e],s=o.readBits(c),n=0;n<s;n++){var d=o.readBits(13),l=Math.floor(d/192)<<8|d%192;l+=l<7936?33088:49472,r.push(l>>8,255&l),t+=String.fromCharCode(a.shiftJISTable[l])}return{bytes:r,text:t}}e.decode=function(o,e){for(var r,a,d,k,u=new s.BitStream(o),C=e<=9?0:e<=26?1:2,m={text:"",bytes:[],chunks:[],version:e};u.available()>=4;){var f=u.readBits(4);if(f===c.Terminator)return m;if(f===c.ECI)0===u.readBits(1)?m.chunks.push({type:t.ECI,assignmentNumber:u.readBits(7)}):0===u.readBits(1)?m.chunks.push({type:t.ECI,assignmentNumber:u.readBits(14)}):0===u.readBits(1)?m.chunks.push({type:t.ECI,assignmentNumber:u.readBits(21)}):m.chunks.push({type:t.ECI,assignmentNumber:-1});else if(f===c.Numeric){var w=n(u,C);m.text+=w.text,(r=m.bytes).push.apply(r,w.bytes),m.chunks.push({type:t.Numeric,text:w.text})}else if(f===c.Alphanumeric){var P=l(u,C);m.text+=P.text,(a=m.bytes).push.apply(a,P.bytes),m.chunks.push({type:t.Alphanumeric,text:P.text})}else if(f===c.Byte){var v=i(u,C);m.text+=v.text,(d=m.bytes).push.apply(d,v.bytes),m.chunks.push({type:t.Byte,bytes:v.bytes,text:v.text})}else if(f===c.Kanji){var h=B(u,C);m.text+=h.text,(k=m.bytes).push.apply(k,h.bytes),m.chunks.push({type:t.Kanji,bytes:h.bytes,text:h.text})}}if(0===u.available()||0===u.readBits(u.available()))return m}},function(o,e,r){"use strict";Object.defineProperty(e,"__esModule",{value:!0});var t=function(){function o(o){this.byteOffset=0,this.bitOffset=0,this.bytes=o}return o.prototype.readBits=function(o){if(o<1||o>32||o>this.available())throw new Error("Cannot read "+o.toString()+" bits");var e=0;if(this.bitOffset>0){var r=8-this.bitOffset,t=o<r?o:r,c=255>>8-t<<(s=r-t);e=(this.bytes[this.byteOffset]&c)>>s,o-=t,this.bitOffset+=t,8===this.bitOffset&&(this.bitOffset=0,this.byteOffset++)}if(o>0){for(;o>=8;)e=e<<8|255&this.bytes[this.byteOffset],this.byteOffset++,o-=8;if(o>0){var s;c=255>>(s=8-o)<<s;e=e<<o|(this.bytes[this.byteOffset]&c)>>s,this.bitOffset+=o}}return e},o.prototype.available=function(){return 8*(this.bytes.length-this.byteOffset)-this.bitOffset},o}();e.BitStream=t},function(o,e,r){"use strict";Object.defineProperty(e,"__esModule",{value:!0}),e.shiftJISTable={32:32,33:33,34:34,35:35,36:36,37:37,38:38,39:39,40:40,41:41,42:42,43:43,44:44,45:45,46:46,47:47,48:48,49:49,50:50,51:51,52:52,53:53,54:54,55:55,56:56,57:57,58:58,59:59,60:60,61:61,62:62,63:63,64:64,65:65,66:66,67:67,68:68,69:69,70:70,71:71,72:72,73:73,74:74,75:75,76:76,77:77,78:78,79:79,80:80,81:81,82:82,83:83,84:84,85:85,86:86,87:87,88:88,89:89,90:90,91:91,92:165,93:93,94:94,95:95,96:96,97:97,98:98,99:99,100:100,101:101,102:102,103:103,104:104,105:105,106:106,107:107,108:108,109:109,110:110,111:111,112:112,113:113,114:114,115:115,116:116,117:117,118:118,119:119,120:120,121:121,122:122,123:123,124:124,125:125,126:8254,33088:12288,33089:12289,33090:12290,33091:65292,33092:65294,33093:12539,33094:65306,33095:65307,33096:65311,33097:65281,33098:12443,33099:12444,33100:180,33101:65344,33102:168,33103:65342,33104:65507,33105:65343,33106:12541,33107:12542,33108:12445,33109:12446,33110:12291,33111:20189,33112:12293,33113:12294,33114:12295,33115:12540,33116:8213,33117:8208,33118:65295,33119:92,33120:12316,33121:8214,33122:65372,33123:8230,33124:8229,33125:8216,33126:8217,33127:8220,33128:8221,33129:65288,33130:65289,33131:12308,33132:12309,33133:65339,33134:65341,33135:65371,33136:65373,33137:12296,33138:12297,33139:12298,33140:12299,33141:12300,33142:12301,33143:12302,33144:12303,33145:12304,33146:12305,33147:65291,33148:8722,33149:177,33150:215,33152:247,33153:65309,33154:8800,33155:65308,33156:65310,33157:8806,33158:8807,33159:8734,33160:8756,33161:9794,33162:9792,33163:176,33164:8242,33165:8243,33166:8451,33167:65509,33168:65284,33169:162,33170:163,33171:65285,33172:65283,33173:65286,33174:65290,33175:65312,33176:167,33177:9734,33178:9733,33179:9675,33180:9679,33181:9678,33182:9671,33183:9670,33184:9633,33185:9632,33186:9651,33187:9650,33188:9661,33189:9660,33190:8251,33191:12306,33192:8594,33193:8592,33194:8593,33195:8595,33196:12307,33208:8712,33209:8715,33210:8838,33211:8839,33212:8834,33213:8835,33214:8746,33215:8745,33224:8743,33225:8744,33226:172,33227:8658,33228:8660,33229:8704,33230:8707,33242:8736,33243:8869,33244:8978,33245:8706,33246:8711,33247:8801,33248:8786,33249:8810,33250:8811,33251:8730,33252:8765,33253:8733,33254:8757,33255:8747,33256:8748,33264:8491,33265:8240,33266:9839,33267:9837,33268:9834,33269:8224,33270:8225,33271:182,33276:9711,33359:65296,33360:65297,33361:65298,33362:65299,33363:65300,33364:65301,33365:65302,33366:65303,33367:65304,33368:65305,33376:65313,33377:65314,33378:65315,33379:65316,33380:65317,33381:65318,33382:65319,33383:65320,33384:65321,33385:65322,33386:65323,33387:65324,33388:65325,33389:65326,33390:65327,33391:65328,33392:65329,33393:65330,33394:65331,33395:65332,33396:65333,33397:65334,33398:65335,33399:65336,33400:65337,33401:65338,33409:65345,33410:65346,33411:65347,33412:65348,33413:65349,33414:65350,33415:65351,33416:65352,33417:65353,33418:65354,33419:65355,33420:65356,33421:65357,33422:65358,33423:65359,33424:65360,33425:65361,33426:65362,33427:65363,33428:65364,33429:65365,33430:65366,33431:65367,33432:65368,33433:65369,33434:65370,33439:12353,33440:12354,33441:12355,33442:12356,33443:12357,33444:12358,33445:12359,33446:12360,33447:12361,33448:12362,33449:12363,33450:12364,33451:12365,33452:12366,33453:12367,33454:12368,33455:12369,33456:12370,33457:12371,33458:12372,33459:12373,33460:12374,33461:12375,33462:12376,33463:12377,33464:12378,33465:12379,33466:12380,33467:12381,33468:12382,33469:12383,33470:12384,33471:12385,33472:12386,33473:12387,33474:12388,33475:12389,33476:12390,33477:12391,33478:12392,33479:12393,33480:12394,33481:12395,33482:12396,33483:12397,33484:12398,33485:12399,33486:12400,33487:12401,33488:12402,33489:12403,33490:12404,33491:12405,33492:12406,33493:12407,33494:12408,33495:12409,33496:12410,33497:12411,33498:12412,33499:12413,33500:12414,33501:12415,33502:12416,33503:12417,33504:12418,33505:12419,33506:12420,33507:12421,33508:12422,33509:12423,33510:12424,33511:12425,33512:12426,33513:12427,33514:12428,33515:12429,33516:12430,33517:12431,33518:12432,33519:12433,33520:12434,33521:12435,33600:12449,33601:12450,33602:12451,33603:12452,33604:12453,33605:12454,33606:12455,33607:12456,33608:12457,33609:12458,33610:12459,33611:12460,33612:12461,33613:12462,33614:12463,33615:12464,33616:12465,33617:12466,33618:12467,33619:12468,33620:12469,33621:12470,33622:12471,33623:12472,33624:12473,33625:12474,33626:12475,33627:12476,33628:12477,33629:12478,33630:12479,33631:12480,33632:12481,33633:12482,33634:12483,33635:12484,33636:12485,33637:12486,33638:12487,33639:12488,33640:12489,33641:12490,33642:12491,33643:12492,33644:12493,33645:12494,33646:12495,33647:12496,33648:12497,33649:12498,33650:12499,33651:12500,33652:12501,33653:12502,33654:12503,33655:12504,33656:12505,33657:12506,33658:12507,33659:12508,33660:12509,33661:12510,33662:12511,33664:12512,33665:12513,33666:12514,33667:12515,33668:12516,33669:12517,33670:12518,33671:12519,33672:12520,33673:12521,33674:12522,33675:12523,33676:12524,33677:12525,33678:12526,33679:12527,33680:12528,33681:12529,33682:12530,33683:12531,33684:12532,33685:12533,33686:12534,33695:913,33696:914,33697:915,33698:916,33699:917,33700:918,33701:919,33702:920,33703:921,33704:922,33705:923,33706:924,33707:925,33708:926,33709:927,33710:928,33711:929,33712:931,33713:932,33714:933,33715:934,33716:935,33717:936,33718:937,33727:945,33728:946,33729:947,33730:948,33731:949,33732:950,33733:951,33734:952,33735:953,33736:954,33737:955,33738:956,33739:957,33740:958,33741:959,33742:960,33743:961,33744:963,33745:964,33746:965,33747:966,33748:967,33749:968,33750:969,33856:1040,33857:1041,33858:1042,33859:1043,33860:1044,33861:1045,33862:1025,33863:1046,33864:1047,33865:1048,33866:1049,33867:1050,33868:1051,33869:1052,33870:1053,33871:1054,33872:1055,33873:1056,33874:1057,33875:1058,33876:1059,33877:1060,33878:1061,33879:1062,33880:1063,33881:1064,33882:1065,33883:1066,33884:1067,33885:1068,33886:1069,33887:1070,33888:1071,33904:1072,33905:1073,33906:1074,33907:1075,33908:1076,33909:1077,33910:1105,33911:1078,33912:1079,33913:1080,33914:1081,33915:1082,33916:1083,33917:1084,33918:1085,33920:1086,33921:1087,33922:1088,33923:1089,33924:1090,33925:1091,33926:1092,33927:1093,33928:1094,33929:1095,33930:1096,33931:1097,33932:1098,33933:1099,33934:1100,33935:1101,33936:1102,33937:1103,33951:9472,33952:9474,33953:9484,33954:9488,33955:9496,33956:9492,33957:9500,33958:9516,33959:9508,33960:9524,33961:9532,33962:9473,33963:9475,33964:9487,33965:9491,33966:9499,33967:9495,33968:9507,33969:9523,33970:9515,33971:9531,33972:9547,33973:9504,33974:9519,33975:9512,33976:9527,33977:9535,33978:9501,33979:9520,33980:9509,33981:9528,33982:9538,34975:20124,34976:21782,34977:23043,34978:38463,34979:21696,34980:24859,34981:25384,34982:23030,34983:36898,34984:33909,34985:33564,34986:31312,34987:24746,34988:25569,34989:28197,34990:26093,34991:33894,34992:33446,34993:39925,34994:26771,34995:22311,34996:26017,34997:25201,34998:23451,34999:22992,35e3:34427,35001:39156,35002:32098,35003:32190,35004:39822,35005:25110,35006:31903,35007:34999,35008:23433,35009:24245,35010:25353,35011:26263,35012:26696,35013:38343,35014:38797,35015:26447,35016:20197,35017:20234,35018:20301,35019:20381,35020:20553,35021:22258,35022:22839,35023:22996,35024:23041,35025:23561,35026:24799,35027:24847,35028:24944,35029:26131,35030:26885,35031:28858,35032:30031,35033:30064,35034:31227,35035:32173,35036:32239,35037:32963,35038:33806,35039:34915,35040:35586,35041:36949,35042:36986,35043:21307,35044:20117,35045:20133,35046:22495,35047:32946,35048:37057,35049:30959,35050:19968,35051:22769,35052:28322,35053:36920,35054:31282,35055:33576,35056:33419,35057:39983,35058:20801,35059:21360,35060:21693,35061:21729,35062:22240,35063:23035,35064:24341,35065:39154,35066:28139,35067:32996,35068:34093,35136:38498,35137:38512,35138:38560,35139:38907,35140:21515,35141:21491,35142:23431,35143:28879,35144:32701,35145:36802,35146:38632,35147:21359,35148:40284,35149:31418,35150:19985,35151:30867,35152:33276,35153:28198,35154:22040,35155:21764,35156:27421,35157:34074,35158:39995,35159:23013,35160:21417,35161:28006,35162:29916,35163:38287,35164:22082,35165:20113,35166:36939,35167:38642,35168:33615,35169:39180,35170:21473,35171:21942,35172:23344,35173:24433,35174:26144,35175:26355,35176:26628,35177:27704,35178:27891,35179:27945,35180:29787,35181:30408,35182:31310,35183:38964,35184:33521,35185:34907,35186:35424,35187:37613,35188:28082,35189:30123,35190:30410,35191:39365,35192:24742,35193:35585,35194:36234,35195:38322,35196:27022,35197:21421,35198:20870,35200:22290,35201:22576,35202:22852,35203:23476,35204:24310,35205:24616,35206:25513,35207:25588,35208:27839,35209:28436,35210:28814,35211:28948,35212:29017,35213:29141,35214:29503,35215:32257,35216:33398,35217:33489,35218:34199,35219:36960,35220:37467,35221:40219,35222:22633,35223:26044,35224:27738,35225:29989,35226:20985,35227:22830,35228:22885,35229:24448,35230:24540,35231:25276,35232:26106,35233:27178,35234:27431,35235:27572,35236:29579,35237:32705,35238:35158,35239:40236,35240:40206,35241:40644,35242:23713,35243:27798,35244:33659,35245:20740,35246:23627,35247:25014,35248:33222,35249:26742,35250:29281,35251:20057,35252:20474,35253:21368,35254:24681,35255:28201,35256:31311,35257:38899,35258:19979,35259:21270,35260:20206,35261:20309,35262:20285,35263:20385,35264:20339,35265:21152,35266:21487,35267:22025,35268:22799,35269:23233,35270:23478,35271:23521,35272:31185,35273:26247,35274:26524,35275:26550,35276:27468,35277:27827,35278:28779,35279:29634,35280:31117,35281:31166,35282:31292,35283:31623,35284:33457,35285:33499,35286:33540,35287:33655,35288:33775,35289:33747,35290:34662,35291:35506,35292:22057,35293:36008,35294:36838,35295:36942,35296:38686,35297:34442,35298:20420,35299:23784,35300:25105,35301:29273,35302:30011,35303:33253,35304:33469,35305:34558,35306:36032,35307:38597,35308:39187,35309:39381,35310:20171,35311:20250,35312:35299,35313:22238,35314:22602,35315:22730,35316:24315,35317:24555,35318:24618,35319:24724,35320:24674,35321:25040,35322:25106,35323:25296,35324:25913,35392:39745,35393:26214,35394:26800,35395:28023,35396:28784,35397:30028,35398:30342,35399:32117,35400:33445,35401:34809,35402:38283,35403:38542,35404:35997,35405:20977,35406:21182,35407:22806,35408:21683,35409:23475,35410:23830,35411:24936,35412:27010,35413:28079,35414:30861,35415:33995,35416:34903,35417:35442,35418:37799,35419:39608,35420:28012,35421:39336,35422:34521,35423:22435,35424:26623,35425:34510,35426:37390,35427:21123,35428:22151,35429:21508,35430:24275,35431:25313,35432:25785,35433:26684,35434:26680,35435:27579,35436:29554,35437:30906,35438:31339,35439:35226,35440:35282,35441:36203,35442:36611,35443:37101,35444:38307,35445:38548,35446:38761,35447:23398,35448:23731,35449:27005,35450:38989,35451:38990,35452:25499,35453:31520,35454:27179,35456:27263,35457:26806,35458:39949,35459:28511,35460:21106,35461:21917,35462:24688,35463:25324,35464:27963,35465:28167,35466:28369,35467:33883,35468:35088,35469:36676,35470:19988,35471:39993,35472:21494,35473:26907,35474:27194,35475:38788,35476:26666,35477:20828,35478:31427,35479:33970,35480:37340,35481:37772,35482:22107,35483:40232,35484:26658,35485:33541,35486:33841,35487:31909,35488:21e3,35489:33477,35490:29926,35491:20094,35492:20355,35493:20896,35494:23506,35495:21002,35496:21208,35497:21223,35498:24059,35499:21914,35500:22570,35501:23014,35502:23436,35503:23448,35504:23515,35505:24178,35506:24185,35507:24739,35508:24863,35509:24931,35510:25022,35511:25563,35512:25954,35513:26577,35514:26707,35515:26874,35516:27454,35517:27475,35518:27735,35519:28450,35520:28567,35521:28485,35522:29872,35523:29976,35524:30435,35525:30475,35526:31487,35527:31649,35528:31777,35529:32233,35530:32566,35531:32752,35532:32925,35533:33382,35534:33694,35535:35251,35536:35532,35537:36011,35538:36996,35539:37969,35540:38291,35541:38289,35542:38306,35543:38501,35544:38867,35545:39208,35546:33304,35547:20024,35548:21547,35549:23736,35550:24012,35551:29609,35552:30284,35553:30524,35554:23721,35555:32747,35556:36107,35557:38593,35558:38929,35559:38996,35560:39e3,35561:20225,35562:20238,35563:21361,35564:21916,35565:22120,35566:22522,35567:22855,35568:23305,35569:23492,35570:23696,35571:24076,35572:24190,35573:24524,35574:25582,35575:26426,35576:26071,35577:26082,35578:26399,35579:26827,35580:26820,35648:27231,35649:24112,35650:27589,35651:27671,35652:27773,35653:30079,35654:31048,35655:23395,35656:31232,35657:32e3,35658:24509,35659:35215,35660:35352,35661:36020,35662:36215,35663:36556,35664:36637,35665:39138,35666:39438,35667:39740,35668:20096,35669:20605,35670:20736,35671:22931,35672:23452,35673:25135,35674:25216,35675:25836,35676:27450,35677:29344,35678:30097,35679:31047,35680:32681,35681:34811,35682:35516,35683:35696,35684:25516,35685:33738,35686:38816,35687:21513,35688:21507,35689:21931,35690:26708,35691:27224,35692:35440,35693:30759,35694:26485,35695:40653,35696:21364,35697:23458,35698:33050,35699:34384,35700:36870,35701:19992,35702:20037,35703:20167,35704:20241,35705:21450,35706:21560,35707:23470,35708:24339,35709:24613,35710:25937,35712:26429,35713:27714,35714:27762,35715:27875,35716:28792,35717:29699,35718:31350,35719:31406,35720:31496,35721:32026,35722:31998,35723:32102,35724:26087,35725:29275,35726:21435,35727:23621,35728:24040,35729:25298,35730:25312,35731:25369,35732:28192,35733:34394,35734:35377,35735:36317,35736:37624,35737:28417,35738:31142,35739:39770,35740:20136,35741:20139,35742:20140,35743:20379,35744:20384,35745:20689,35746:20807,35747:31478,35748:20849,35749:20982,35750:21332,35751:21281,35752:21375,35753:21483,35754:21932,35755:22659,35756:23777,35757:24375,35758:24394,35759:24623,35760:24656,35761:24685,35762:25375,35763:25945,35764:27211,35765:27841,35766:29378,35767:29421,35768:30703,35769:33016,35770:33029,35771:33288,35772:34126,35773:37111,35774:37857,35775:38911,35776:39255,35777:39514,35778:20208,35779:20957,35780:23597,35781:26241,35782:26989,35783:23616,35784:26354,35785:26997,35786:29577,35787:26704,35788:31873,35789:20677,35790:21220,35791:22343,35792:24062,35793:37670,35794:26020,35795:27427,35796:27453,35797:29748,35798:31105,35799:31165,35800:31563,35801:32202,35802:33465,35803:33740,35804:34943,35805:35167,35806:35641,35807:36817,35808:37329,35809:21535,35810:37504,35811:20061,35812:20534,35813:21477,35814:21306,35815:29399,35816:29590,35817:30697,35818:33510,35819:36527,35820:39366,35821:39368,35822:39378,35823:20855,35824:24858,35825:34398,35826:21936,35827:31354,35828:20598,35829:23507,35830:36935,35831:38533,35832:20018,35833:27355,35834:37351,35835:23633,35836:23624,35904:25496,35905:31391,35906:27795,35907:38772,35908:36705,35909:31402,35910:29066,35911:38536,35912:31874,35913:26647,35914:32368,35915:26705,35916:37740,35917:21234,35918:21531,35919:34219,35920:35347,35921:32676,35922:36557,35923:37089,35924:21350,35925:34952,35926:31041,35927:20418,35928:20670,35929:21009,35930:20804,35931:21843,35932:22317,35933:29674,35934:22411,35935:22865,35936:24418,35937:24452,35938:24693,35939:24950,35940:24935,35941:25001,35942:25522,35943:25658,35944:25964,35945:26223,35946:26690,35947:28179,35948:30054,35949:31293,35950:31995,35951:32076,35952:32153,35953:32331,35954:32619,35955:33550,35956:33610,35957:34509,35958:35336,35959:35427,35960:35686,35961:36605,35962:38938,35963:40335,35964:33464,35965:36814,35966:39912,35968:21127,35969:25119,35970:25731,35971:28608,35972:38553,35973:26689,35974:20625,35975:27424,35976:27770,35977:28500,35978:31348,35979:32080,35980:34880,35981:35363,35982:26376,35983:20214,35984:20537,35985:20518,35986:20581,35987:20860,35988:21048,35989:21091,35990:21927,35991:22287,35992:22533,35993:23244,35994:24314,35995:25010,35996:25080,35997:25331,35998:25458,35999:26908,36e3:27177,36001:29309,36002:29356,36003:29486,36004:30740,36005:30831,36006:32121,36007:30476,36008:32937,36009:35211,36010:35609,36011:36066,36012:36562,36013:36963,36014:37749,36015:38522,36016:38997,36017:39443,36018:40568,36019:20803,36020:21407,36021:21427,36022:24187,36023:24358,36024:28187,36025:28304,36026:29572,36027:29694,36028:32067,36029:33335,36030:35328,36031:35578,36032:38480,36033:20046,36034:20491,36035:21476,36036:21628,36037:22266,36038:22993,36039:23396,36040:24049,36041:24235,36042:24359,36043:25144,36044:25925,36045:26543,36046:28246,36047:29392,36048:31946,36049:34996,36050:32929,36051:32993,36052:33776,36053:34382,36054:35463,36055:36328,36056:37431,36057:38599,36058:39015,36059:40723,36060:20116,36061:20114,36062:20237,36063:21320,36064:21577,36065:21566,36066:23087,36067:24460,36068:24481,36069:24735,36070:26791,36071:27278,36072:29786,36073:30849,36074:35486,36075:35492,36076:35703,36077:37264,36078:20062,36079:39881,36080:20132,36081:20348,36082:20399,36083:20505,36084:20502,36085:20809,36086:20844,36087:21151,36088:21177,36089:21246,36090:21402,36091:21475,36092:21521,36160:21518,36161:21897,36162:22353,36163:22434,36164:22909,36165:23380,36166:23389,36167:23439,36168:24037,36169:24039,36170:24055,36171:24184,36172:24195,36173:24218,36174:24247,36175:24344,36176:24658,36177:24908,36178:25239,36179:25304,36180:25511,36181:25915,36182:26114,36183:26179,36184:26356,36185:26477,36186:26657,36187:26775,36188:27083,36189:27743,36190:27946,36191:28009,36192:28207,36193:28317,36194:30002,36195:30343,36196:30828,36197:31295,36198:31968,36199:32005,36200:32024,36201:32094,36202:32177,36203:32789,36204:32771,36205:32943,36206:32945,36207:33108,36208:33167,36209:33322,36210:33618,36211:34892,36212:34913,36213:35611,36214:36002,36215:36092,36216:37066,36217:37237,36218:37489,36219:30783,36220:37628,36221:38308,36222:38477,36224:38917,36225:39321,36226:39640,36227:40251,36228:21083,36229:21163,36230:21495,36231:21512,36232:22741,36233:25335,36234:28640,36235:35946,36236:36703,36237:40633,36238:20811,36239:21051,36240:21578,36241:22269,36242:31296,36243:37239,36244:40288,36245:40658,36246:29508,36247:28425,36248:33136,36249:29969,36250:24573,36251:24794,36252:39592,36253:29403,36254:36796,36255:27492,36256:38915,36257:20170,36258:22256,36259:22372,36260:22718,36261:23130,36262:24680,36263:25031,36264:26127,36265:26118,36266:26681,36267:26801,36268:28151,36269:30165,36270:32058,36271:33390,36272:39746,36273:20123,36274:20304,36275:21449,36276:21766,36277:23919,36278:24038,36279:24046,36280:26619,36281:27801,36282:29811,36283:30722,36284:35408,36285:37782,36286:35039,36287:22352,36288:24231,36289:25387,36290:20661,36291:20652,36292:20877,36293:26368,36294:21705,36295:22622,36296:22971,36297:23472,36298:24425,36299:25165,36300:25505,36301:26685,36302:27507,36303:28168,36304:28797,36305:37319,36306:29312,36307:30741,36308:30758,36309:31085,36310:25998,36311:32048,36312:33756,36313:35009,36314:36617,36315:38555,36316:21092,36317:22312,36318:26448,36319:32618,36320:36001,36321:20916,36322:22338,36323:38442,36324:22586,36325:27018,36326:32948,36327:21682,36328:23822,36329:22524,36330:30869,36331:40442,36332:20316,36333:21066,36334:21643,36335:25662,36336:26152,36337:26388,36338:26613,36339:31364,36340:31574,36341:32034,36342:37679,36343:26716,36344:39853,36345:31545,36346:21273,36347:20874,36348:21047,36416:23519,36417:25334,36418:25774,36419:25830,36420:26413,36421:27578,36422:34217,36423:38609,36424:30352,36425:39894,36426:25420,36427:37638,36428:39851,36429:30399,36430:26194,36431:19977,36432:20632,36433:21442,36434:23665,36435:24808,36436:25746,36437:25955,36438:26719,36439:29158,36440:29642,36441:29987,36442:31639,36443:32386,36444:34453,36445:35715,36446:36059,36447:37240,36448:39184,36449:26028,36450:26283,36451:27531,36452:20181,36453:20180,36454:20282,36455:20351,36456:21050,36457:21496,36458:21490,36459:21987,36460:22235,36461:22763,36462:22987,36463:22985,36464:23039,36465:23376,36466:23629,36467:24066,36468:24107,36469:24535,36470:24605,36471:25351,36472:25903,36473:23388,36474:26031,36475:26045,36476:26088,36477:26525,36478:27490,36480:27515,36481:27663,36482:29509,36483:31049,36484:31169,36485:31992,36486:32025,36487:32043,36488:32930,36489:33026,36490:33267,36491:35222,36492:35422,36493:35433,36494:35430,36495:35468,36496:35566,36497:36039,36498:36060,36499:38604,36500:39164,36501:27503,36502:20107,36503:20284,36504:20365,36505:20816,36506:23383,36507:23546,36508:24904,36509:25345,36510:26178,36511:27425,36512:28363,36513:27835,36514:29246,36515:29885,36516:30164,36517:30913,36518:31034,36519:32780,36520:32819,36521:33258,36522:33940,36523:36766,36524:27728,36525:40575,36526:24335,36527:35672,36528:40235,36529:31482,36530:36600,36531:23437,36532:38635,36533:19971,36534:21489,36535:22519,36536:22833,36537:23241,36538:23460,36539:24713,36540:28287,36541:28422,36542:30142,36543:36074,36544:23455,36545:34048,36546:31712,36547:20594,36548:26612,36549:33437,36550:23649,36551:34122,36552:32286,36553:33294,36554:20889,36555:23556,36556:25448,36557:36198,36558:26012,36559:29038,36560:31038,36561:32023,36562:32773,36563:35613,36564:36554,36565:36974,36566:34503,36567:37034,36568:20511,36569:21242,36570:23610,36571:26451,36572:28796,36573:29237,36574:37196,36575:37320,36576:37675,36577:33509,36578:23490,36579:24369,36580:24825,36581:20027,36582:21462,36583:23432,36584:25163,36585:26417,36586:27530,36587:29417,36588:29664,36589:31278,36590:33131,36591:36259,36592:37202,36593:39318,36594:20754,36595:21463,36596:21610,36597:23551,36598:25480,36599:27193,36600:32172,36601:38656,36602:22234,36603:21454,36604:21608,36672:23447,36673:23601,36674:24030,36675:20462,36676:24833,36677:25342,36678:27954,36679:31168,36680:31179,36681:32066,36682:32333,36683:32722,36684:33261,36685:33311,36686:33936,36687:34886,36688:35186,36689:35728,36690:36468,36691:36655,36692:36913,36693:37195,36694:37228,36695:38598,36696:37276,36697:20160,36698:20303,36699:20805,36700:21313,36701:24467,36702:25102,36703:26580,36704:27713,36705:28171,36706:29539,36707:32294,36708:37325,36709:37507,36710:21460,36711:22809,36712:23487,36713:28113,36714:31069,36715:32302,36716:31899,36717:22654,36718:29087,36719:20986,36720:34899,36721:36848,36722:20426,36723:23803,36724:26149,36725:30636,36726:31459,36727:33308,36728:39423,36729:20934,36730:24490,36731:26092,36732:26991,36733:27529,36734:28147,36736:28310,36737:28516,36738:30462,36739:32020,36740:24033,36741:36981,36742:37255,36743:38918,36744:20966,36745:21021,36746:25152,36747:26257,36748:26329,36749:28186,36750:24246,36751:32210,36752:32626,36753:26360,36754:34223,36755:34295,36756:35576,36757:21161,36758:21465,36759:22899,36760:24207,36761:24464,36762:24661,36763:37604,36764:38500,36765:20663,36766:20767,36767:21213,36768:21280,36769:21319,36770:21484,36771:21736,36772:21830,36773:21809,36774:22039,36775:22888,36776:22974,36777:23100,36778:23477,36779:23558,36780:23567,36781:23569,36782:23578,36783:24196,36784:24202,36785:24288,36786:24432,36787:25215,36788:25220,36789:25307,36790:25484,36791:25463,36792:26119,36793:26124,36794:26157,36795:26230,36796:26494,36797:26786,36798:27167,36799:27189,36800:27836,36801:28040,36802:28169,36803:28248,36804:28988,36805:28966,36806:29031,36807:30151,36808:30465,36809:30813,36810:30977,36811:31077,36812:31216,36813:31456,36814:31505,36815:31911,36816:32057,36817:32918,36818:33750,36819:33931,36820:34121,36821:34909,36822:35059,36823:35359,36824:35388,36825:35412,36826:35443,36827:35937,36828:36062,36829:37284,36830:37478,36831:37758,36832:37912,36833:38556,36834:38808,36835:19978,36836:19976,36837:19998,36838:20055,36839:20887,36840:21104,36841:22478,36842:22580,36843:22732,36844:23330,36845:24120,36846:24773,36847:25854,36848:26465,36849:26454,36850:27972,36851:29366,36852:30067,36853:31331,36854:33976,36855:35698,36856:37304,36857:37664,36858:22065,36859:22516,36860:39166,36928:25325,36929:26893,36930:27542,36931:29165,36932:32340,36933:32887,36934:33394,36935:35302,36936:39135,36937:34645,36938:36785,36939:23611,36940:20280,36941:20449,36942:20405,36943:21767,36944:23072,36945:23517,36946:23529,36947:24515,36948:24910,36949:25391,36950:26032,36951:26187,36952:26862,36953:27035,36954:28024,36955:28145,36956:30003,36957:30137,36958:30495,36959:31070,36960:31206,36961:32051,36962:33251,36963:33455,36964:34218,36965:35242,36966:35386,36967:36523,36968:36763,36969:36914,36970:37341,36971:38663,36972:20154,36973:20161,36974:20995,36975:22645,36976:22764,36977:23563,36978:29978,36979:23613,36980:33102,36981:35338,36982:36805,36983:38499,36984:38765,36985:31525,36986:35535,36987:38920,36988:37218,36989:22259,36990:21416,36992:36887,36993:21561,36994:22402,36995:24101,36996:25512,36997:27700,36998:28810,36999:30561,37e3:31883,37001:32736,37002:34928,37003:36930,37004:37204,37005:37648,37006:37656,37007:38543,37008:29790,37009:39620,37010:23815,37011:23913,37012:25968,37013:26530,37014:36264,37015:38619,37016:25454,37017:26441,37018:26905,37019:33733,37020:38935,37021:38592,37022:35070,37023:28548,37024:25722,37025:23544,37026:19990,37027:28716,37028:30045,37029:26159,37030:20932,37031:21046,37032:21218,37033:22995,37034:24449,37035:24615,37036:25104,37037:25919,37038:25972,37039:26143,37040:26228,37041:26866,37042:26646,37043:27491,37044:28165,37045:29298,37046:29983,37047:30427,37048:31934,37049:32854,37050:22768,37051:35069,37052:35199,37053:35488,37054:35475,37055:35531,37056:36893,37057:37266,37058:38738,37059:38745,37060:25993,37061:31246,37062:33030,37063:38587,37064:24109,37065:24796,37066:25114,37067:26021,37068:26132,37069:26512,37070:30707,37071:31309,37072:31821,37073:32318,37074:33034,37075:36012,37076:36196,37077:36321,37078:36447,37079:30889,37080:20999,37081:25305,37082:25509,37083:25666,37084:25240,37085:35373,37086:31363,37087:31680,37088:35500,37089:38634,37090:32118,37091:33292,37092:34633,37093:20185,37094:20808,37095:21315,37096:21344,37097:23459,37098:23554,37099:23574,37100:24029,37101:25126,37102:25159,37103:25776,37104:26643,37105:26676,37106:27849,37107:27973,37108:27927,37109:26579,37110:28508,37111:29006,37112:29053,37113:26059,37114:31359,37115:31661,37116:32218,37184:32330,37185:32680,37186:33146,37187:33307,37188:33337,37189:34214,37190:35438,37191:36046,37192:36341,37193:36984,37194:36983,37195:37549,37196:37521,37197:38275,37198:39854,37199:21069,37200:21892,37201:28472,37202:28982,37203:20840,37204:31109,37205:32341,37206:33203,37207:31950,37208:22092,37209:22609,37210:23720,37211:25514,37212:26366,37213:26365,37214:26970,37215:29401,37216:30095,37217:30094,37218:30990,37219:31062,37220:31199,37221:31895,37222:32032,37223:32068,37224:34311,37225:35380,37226:38459,37227:36961,37228:40736,37229:20711,37230:21109,37231:21452,37232:21474,37233:20489,37234:21930,37235:22766,37236:22863,37237:29245,37238:23435,37239:23652,37240:21277,37241:24803,37242:24819,37243:25436,37244:25475,37245:25407,37246:25531,37248:25805,37249:26089,37250:26361,37251:24035,37252:27085,37253:27133,37254:28437,37255:29157,37256:20105,37257:30185,37258:30456,37259:31379,37260:31967,37261:32207,37262:32156,37263:32865,37264:33609,37265:33624,37266:33900,37267:33980,37268:34299,37269:35013,37270:36208,37271:36865,37272:36973,37273:37783,37274:38684,37275:39442,37276:20687,37277:22679,37278:24974,37279:33235,37280:34101,37281:36104,37282:36896,37283:20419,37284:20596,37285:21063,37286:21363,37287:24687,37288:25417,37289:26463,37290:28204,37291:36275,37292:36895,37293:20439,37294:23646,37295:36042,37296:26063,37297:32154,37298:21330,37299:34966,37300:20854,37301:25539,37302:23384,37303:23403,37304:23562,37305:25613,37306:26449,37307:36956,37308:20182,37309:22810,37310:22826,37311:27760,37312:35409,37313:21822,37314:22549,37315:22949,37316:24816,37317:25171,37318:26561,37319:33333,37320:26965,37321:38464,37322:39364,37323:39464,37324:20307,37325:22534,37326:23550,37327:32784,37328:23729,37329:24111,37330:24453,37331:24608,37332:24907,37333:25140,37334:26367,37335:27888,37336:28382,37337:32974,37338:33151,37339:33492,37340:34955,37341:36024,37342:36864,37343:36910,37344:38538,37345:40667,37346:39899,37347:20195,37348:21488,37349:22823,37350:31532,37351:37261,37352:38988,37353:40441,37354:28381,37355:28711,37356:21331,37357:21828,37358:23429,37359:25176,37360:25246,37361:25299,37362:27810,37363:28655,37364:29730,37365:35351,37366:37944,37367:28609,37368:35582,37369:33592,37370:20967,37371:34552,37372:21482,37440:21481,37441:20294,37442:36948,37443:36784,37444:22890,37445:33073,37446:24061,37447:31466,37448:36799,37449:26842,37450:35895,37451:29432,37452:40008,37453:27197,37454:35504,37455:20025,37456:21336,37457:22022,37458:22374,37459:25285,37460:25506,37461:26086,37462:27470,37463:28129,37464:28251,37465:28845,37466:30701,37467:31471,37468:31658,37469:32187,37470:32829,37471:32966,37472:34507,37473:35477,37474:37723,37475:22243,37476:22727,37477:24382,37478:26029,37479:26262,37480:27264,37481:27573,37482:30007,37483:35527,37484:20516,37485:30693,37486:22320,37487:24347,37488:24677,37489:26234,37490:27744,37491:30196,37492:31258,37493:32622,37494:33268,37495:34584,37496:36933,37497:39347,37498:31689,37499:30044,37500:31481,37501:31569,37502:33988,37504:36880,37505:31209,37506:31378,37507:33590,37508:23265,37509:30528,37510:20013,37511:20210,37512:23449,37513:24544,37514:25277,37515:26172,37516:26609,37517:27880,37518:34411,37519:34935,37520:35387,37521:37198,37522:37619,37523:39376,37524:27159,37525:28710,37526:29482,37527:33511,37528:33879,37529:36015,37530:19969,37531:20806,37532:20939,37533:21899,37534:23541,37535:24086,37536:24115,37537:24193,37538:24340,37539:24373,37540:24427,37541:24500,37542:25074,37543:25361,37544:26274,37545:26397,37546:28526,37547:29266,37548:30010,37549:30522,37550:32884,37551:33081,37552:33144,37553:34678,37554:35519,37555:35548,37556:36229,37557:36339,37558:37530,37559:38263,37560:38914,37561:40165,37562:21189,37563:25431,37564:30452,37565:26389,37566:27784,37567:29645,37568:36035,37569:37806,37570:38515,37571:27941,37572:22684,37573:26894,37574:27084,37575:36861,37576:37786,37577:30171,37578:36890,37579:22618,37580:26626,37581:25524,37582:27131,37583:20291,37584:28460,37585:26584,37586:36795,37587:34086,37588:32180,37589:37716,37590:26943,37591:28528,37592:22378,37593:22775,37594:23340,37595:32044,37596:29226,37597:21514,37598:37347,37599:40372,37600:20141,37601:20302,37602:20572,37603:20597,37604:21059,37605:35998,37606:21576,37607:22564,37608:23450,37609:24093,37610:24213,37611:24237,37612:24311,37613:24351,37614:24716,37615:25269,37616:25402,37617:25552,37618:26799,37619:27712,37620:30855,37621:31118,37622:31243,37623:32224,37624:33351,37625:35330,37626:35558,37627:36420,37628:36883,37696:37048,37697:37165,37698:37336,37699:40718,37700:27877,37701:25688,37702:25826,37703:25973,37704:28404,37705:30340,37706:31515,37707:36969,37708:37841,37709:28346,37710:21746,37711:24505,37712:25764,37713:36685,37714:36845,37715:37444,37716:20856,37717:22635,37718:22825,37719:23637,37720:24215,37721:28155,37722:32399,37723:29980,37724:36028,37725:36578,37726:39003,37727:28857,37728:20253,37729:27583,37730:28593,37731:3e4,37732:38651,37733:20814,37734:21520,37735:22581,37736:22615,37737:22956,37738:23648,37739:24466,37740:26007,37741:26460,37742:28193,37743:30331,37744:33759,37745:36077,37746:36884,37747:37117,37748:37709,37749:30757,37750:30778,37751:21162,37752:24230,37753:22303,37754:22900,37755:24594,37756:20498,37757:20826,37758:20908,37760:20941,37761:20992,37762:21776,37763:22612,37764:22616,37765:22871,37766:23445,37767:23798,37768:23947,37769:24764,37770:25237,37771:25645,37772:26481,37773:26691,37774:26812,37775:26847,37776:30423,37777:28120,37778:28271,37779:28059,37780:28783,37781:29128,37782:24403,37783:30168,37784:31095,37785:31561,37786:31572,37787:31570,37788:31958,37789:32113,37790:21040,37791:33891,37792:34153,37793:34276,37794:35342,37795:35588,37796:35910,37797:36367,37798:36867,37799:36879,37800:37913,37801:38518,37802:38957,37803:39472,37804:38360,37805:20685,37806:21205,37807:21516,37808:22530,37809:23566,37810:24999,37811:25758,37812:27934,37813:30643,37814:31461,37815:33012,37816:33796,37817:36947,37818:37509,37819:23776,37820:40199,37821:21311,37822:24471,37823:24499,37824:28060,37825:29305,37826:30563,37827:31167,37828:31716,37829:27602,37830:29420,37831:35501,37832:26627,37833:27233,37834:20984,37835:31361,37836:26932,37837:23626,37838:40182,37839:33515,37840:23493,37841:37193,37842:28702,37843:22136,37844:23663,37845:24775,37846:25958,37847:27788,37848:35930,37849:36929,37850:38931,37851:21585,37852:26311,37853:37389,37854:22856,37855:37027,37856:20869,37857:20045,37858:20970,37859:34201,37860:35598,37861:28760,37862:25466,37863:37707,37864:26978,37865:39348,37866:32260,37867:30071,37868:21335,37869:26976,37870:36575,37871:38627,37872:27741,37873:20108,37874:23612,37875:24336,37876:36841,37877:21250,37878:36049,37879:32905,37880:34425,37881:24319,37882:26085,37883:20083,37884:20837,37952:22914,37953:23615,37954:38894,37955:20219,37956:22922,37957:24525,37958:35469,37959:28641,37960:31152,37961:31074,37962:23527,37963:33905,37964:29483,37965:29105,37966:24180,37967:24565,37968:25467,37969:25754,37970:29123,37971:31896,37972:20035,37973:24316,37974:20043,37975:22492,37976:22178,37977:24745,37978:28611,37979:32013,37980:33021,37981:33075,37982:33215,37983:36786,37984:35223,37985:34468,37986:24052,37987:25226,37988:25773,37989:35207,37990:26487,37991:27874,37992:27966,37993:29750,37994:30772,37995:23110,37996:32629,37997:33453,37998:39340,37999:20467,38e3:24259,38001:25309,38002:25490,38003:25943,38004:26479,38005:30403,38006:29260,38007:32972,38008:32954,38009:36649,38010:37197,38011:20493,38012:22521,38013:23186,38014:26757,38016:26995,38017:29028,38018:29437,38019:36023,38020:22770,38021:36064,38022:38506,38023:36889,38024:34687,38025:31204,38026:30695,38027:33833,38028:20271,38029:21093,38030:21338,38031:25293,38032:26575,38033:27850,38034:30333,38035:31636,38036:31893,38037:33334,38038:34180,38039:36843,38040:26333,38041:28448,38042:29190,38043:32283,38044:33707,38045:39361,38046:40614,38047:20989,38048:31665,38049:30834,38050:31672,38051:32903,38052:31560,38053:27368,38054:24161,38055:32908,38056:30033,38057:30048,38058:20843,38059:37474,38060:28300,38061:30330,38062:37271,38063:39658,38064:20240,38065:32624,38066:25244,38067:31567,38068:38309,38069:40169,38070:22138,38071:22617,38072:34532,38073:38588,38074:20276,38075:21028,38076:21322,38077:21453,38078:21467,38079:24070,38080:25644,38081:26001,38082:26495,38083:27710,38084:27726,38085:29256,38086:29359,38087:29677,38088:30036,38089:32321,38090:33324,38091:34281,38092:36009,38093:31684,38094:37318,38095:29033,38096:38930,38097:39151,38098:25405,38099:26217,38100:30058,38101:30436,38102:30928,38103:34115,38104:34542,38105:21290,38106:21329,38107:21542,38108:22915,38109:24199,38110:24444,38111:24754,38112:25161,38113:25209,38114:25259,38115:26e3,38116:27604,38117:27852,38118:30130,38119:30382,38120:30865,38121:31192,38122:32203,38123:32631,38124:32933,38125:34987,38126:35513,38127:36027,38128:36991,38129:38750,38130:39131,38131:27147,38132:31800,38133:20633,38134:23614,38135:24494,38136:26503,38137:27608,38138:29749,38139:30473,38140:32654,38208:40763,38209:26570,38210:31255,38211:21305,38212:30091,38213:39661,38214:24422,38215:33181,38216:33777,38217:32920,38218:24380,38219:24517,38220:30050,38221:31558,38222:36924,38223:26727,38224:23019,38225:23195,38226:32016,38227:30334,38228:35628,38229:20469,38230:24426,38231:27161,38232:27703,38233:28418,38234:29922,38235:31080,38236:34920,38237:35413,38238:35961,38239:24287,38240:25551,38241:30149,38242:31186,38243:33495,38244:37672,38245:37618,38246:33948,38247:34541,38248:39981,38249:21697,38250:24428,38251:25996,38252:27996,38253:28693,38254:36007,38255:36051,38256:38971,38257:25935,38258:29942,38259:19981,38260:20184,38261:22496,38262:22827,38263:23142,38264:23500,38265:20904,38266:24067,38267:24220,38268:24598,38269:25206,38270:25975,38272:26023,38273:26222,38274:28014,38275:29238,38276:31526,38277:33104,38278:33178,38279:33433,38280:35676,38281:36e3,38282:36070,38283:36212,38284:38428,38285:38468,38286:20398,38287:25771,38288:27494,38289:33310,38290:33889,38291:34154,38292:37096,38293:23553,38294:26963,38295:39080,38296:33914,38297:34135,38298:20239,38299:21103,38300:24489,38301:24133,38302:26381,38303:31119,38304:33145,38305:35079,38306:35206,38307:28149,38308:24343,38309:25173,38310:27832,38311:20175,38312:29289,38313:39826,38314:20998,38315:21563,38316:22132,38317:22707,38318:24996,38319:25198,38320:28954,38321:22894,38322:31881,38323:31966,38324:32027,38325:38640,38326:25991,38327:32862,38328:19993,38329:20341,38330:20853,38331:22592,38332:24163,38333:24179,38334:24330,38335:26564,38336:20006,38337:34109,38338:38281,38339:38491,38340:31859,38341:38913,38342:20731,38343:22721,38344:30294,38345:30887,38346:21029,38347:30629,38348:34065,38349:31622,38350:20559,38351:22793,38352:29255,38353:31687,38354:32232,38355:36794,38356:36820,38357:36941,38358:20415,38359:21193,38360:23081,38361:24321,38362:38829,38363:20445,38364:33303,38365:37610,38366:22275,38367:25429,38368:27497,38369:29995,38370:35036,38371:36628,38372:31298,38373:21215,38374:22675,38375:24917,38376:25098,38377:26286,38378:27597,38379:31807,38380:33769,38381:20515,38382:20472,38383:21253,38384:21574,38385:22577,38386:22857,38387:23453,38388:23792,38389:23791,38390:23849,38391:24214,38392:25265,38393:25447,38394:25918,38395:26041,38396:26379,38464:27861,38465:27873,38466:28921,38467:30770,38468:32299,38469:32990,38470:33459,38471:33804,38472:34028,38473:34562,38474:35090,38475:35370,38476:35914,38477:37030,38478:37586,38479:39165,38480:40179,38481:40300,38482:20047,38483:20129,38484:20621,38485:21078,38486:22346,38487:22952,38488:24125,38489:24536,38490:24537,38491:25151,38492:26292,38493:26395,38494:26576,38495:26834,38496:20882,38497:32033,38498:32938,38499:33192,38500:35584,38501:35980,38502:36031,38503:37502,38504:38450,38505:21536,38506:38956,38507:21271,38508:20693,38509:21340,38510:22696,38511:25778,38512:26420,38513:29287,38514:30566,38515:31302,38516:37350,38517:21187,38518:27809,38519:27526,38520:22528,38521:24140,38522:22868,38523:26412,38524:32763,38525:20961,38526:30406,38528:25705,38529:30952,38530:39764,38531:40635,38532:22475,38533:22969,38534:26151,38535:26522,38536:27598,38537:21737,38538:27097,38539:24149,38540:33180,38541:26517,38542:39850,38543:26622,38544:40018,38545:26717,38546:20134,38547:20451,38548:21448,38549:25273,38550:26411,38551:27819,38552:36804,38553:20397,38554:32365,38555:40639,38556:19975,38557:24930,38558:28288,38559:28459,38560:34067,38561:21619,38562:26410,38563:39749,38564:24051,38565:31637,38566:23724,38567:23494,38568:34588,38569:28234,38570:34001,38571:31252,38572:33032,38573:22937,38574:31885,38575:27665,38576:30496,38577:21209,38578:22818,38579:28961,38580:29279,38581:30683,38582:38695,38583:40289,38584:26891,38585:23167,38586:23064,38587:20901,38588:21517,38589:21629,38590:26126,38591:30431,38592:36855,38593:37528,38594:40180,38595:23018,38596:29277,38597:28357,38598:20813,38599:26825,38600:32191,38601:32236,38602:38754,38603:40634,38604:25720,38605:27169,38606:33538,38607:22916,38608:23391,38609:27611,38610:29467,38611:30450,38612:32178,38613:32791,38614:33945,38615:20786,38616:26408,38617:40665,38618:30446,38619:26466,38620:21247,38621:39173,38622:23588,38623:25147,38624:31870,38625:36016,38626:21839,38627:24758,38628:32011,38629:38272,38630:21249,38631:20063,38632:20918,38633:22812,38634:29242,38635:32822,38636:37326,38637:24357,38638:30690,38639:21380,38640:24441,38641:32004,38642:34220,38643:35379,38644:36493,38645:38742,38646:26611,38647:34222,38648:37971,38649:24841,38650:24840,38651:27833,38652:30290,38720:35565,38721:36664,38722:21807,38723:20305,38724:20778,38725:21191,38726:21451,38727:23461,38728:24189,38729:24736,38730:24962,38731:25558,38732:26377,38733:26586,38734:28263,38735:28044,38736:29494,38737:29495,38738:30001,38739:31056,38740:35029,38741:35480,38742:36938,38743:37009,38744:37109,38745:38596,38746:34701,38747:22805,38748:20104,38749:20313,38750:19982,38751:35465,38752:36671,38753:38928,38754:20653,38755:24188,38756:22934,38757:23481,38758:24248,38759:25562,38760:25594,38761:25793,38762:26332,38763:26954,38764:27096,38765:27915,38766:28342,38767:29076,38768:29992,38769:31407,38770:32650,38771:32768,38772:33865,38773:33993,38774:35201,38775:35617,38776:36362,38777:36965,38778:38525,38779:39178,38780:24958,38781:25233,38782:27442,38784:27779,38785:28020,38786:32716,38787:32764,38788:28096,38789:32645,38790:34746,38791:35064,38792:26469,38793:33713,38794:38972,38795:38647,38796:27931,38797:32097,38798:33853,38799:37226,38800:20081,38801:21365,38802:23888,38803:27396,38804:28651,38805:34253,38806:34349,38807:35239,38808:21033,38809:21519,38810:23653,38811:26446,38812:26792,38813:29702,38814:29827,38815:30178,38816:35023,38817:35041,38818:37324,38819:38626,38820:38520,38821:24459,38822:29575,38823:31435,38824:33870,38825:25504,38826:30053,38827:21129,38828:27969,38829:28316,38830:29705,38831:30041,38832:30827,38833:31890,38834:38534,38835:31452,38836:40845,38837:20406,38838:24942,38839:26053,38840:34396,38841:20102,38842:20142,38843:20698,38844:20001,38845:20940,38846:23534,38847:26009,38848:26753,38849:28092,38850:29471,38851:30274,38852:30637,38853:31260,38854:31975,38855:33391,38856:35538,38857:36988,38858:37327,38859:38517,38860:38936,38861:21147,38862:32209,38863:20523,38864:21400,38865:26519,38866:28107,38867:29136,38868:29747,38869:33256,38870:36650,38871:38563,38872:40023,38873:40607,38874:29792,38875:22593,38876:28057,38877:32047,38878:39006,38879:20196,38880:20278,38881:20363,38882:20919,38883:21169,38884:23994,38885:24604,38886:29618,38887:31036,38888:33491,38889:37428,38890:38583,38891:38646,38892:38666,38893:40599,38894:40802,38895:26278,38896:27508,38897:21015,38898:21155,38899:28872,38900:35010,38901:24265,38902:24651,38903:24976,38904:28451,38905:29001,38906:31806,38907:32244,38908:32879,38976:34030,38977:36899,38978:37676,38979:21570,38980:39791,38981:27347,38982:28809,38983:36034,38984:36335,38985:38706,38986:21172,38987:23105,38988:24266,38989:24324,38990:26391,38991:27004,38992:27028,38993:28010,38994:28431,38995:29282,38996:29436,38997:31725,38998:32769,38999:32894,39e3:34635,39001:37070,39002:20845,39003:40595,39004:31108,39005:32907,39006:37682,39007:35542,39008:20525,39009:21644,39010:35441,39011:27498,39012:36036,39013:33031,39014:24785,39015:26528,39016:40434,39017:20121,39018:20120,39019:39952,39020:35435,39021:34241,39022:34152,39023:26880,39024:28286,39025:30871,39026:33109,39071:24332,39072:19984,39073:19989,39074:20010,39075:20017,39076:20022,39077:20028,39078:20031,39079:20034,39080:20054,39081:20056,39082:20098,39083:20101,39084:35947,39085:20106,39086:33298,39087:24333,39088:20110,39089:20126,39090:20127,39091:20128,39092:20130,39093:20144,39094:20147,39095:20150,39096:20174,39097:20173,39098:20164,39099:20166,39100:20162,39101:20183,39102:20190,39103:20205,39104:20191,39105:20215,39106:20233,39107:20314,39108:20272,39109:20315,39110:20317,39111:20311,39112:20295,39113:20342,39114:20360,39115:20367,39116:20376,39117:20347,39118:20329,39119:20336,39120:20369,39121:20335,39122:20358,39123:20374,39124:20760,39125:20436,39126:20447,39127:20430,39128:20440,39129:20443,39130:20433,39131:20442,39132:20432,39133:20452,39134:20453,39135:20506,39136:20520,39137:20500,39138:20522,39139:20517,39140:20485,39141:20252,39142:20470,39143:20513,39144:20521,39145:20524,39146:20478,39147:20463,39148:20497,39149:20486,39150:20547,39151:20551,39152:26371,39153:20565,39154:20560,39155:20552,39156:20570,39157:20566,39158:20588,39159:20600,39160:20608,39161:20634,39162:20613,39163:20660,39164:20658,39232:20681,39233:20682,39234:20659,39235:20674,39236:20694,39237:20702,39238:20709,39239:20717,39240:20707,39241:20718,39242:20729,39243:20725,39244:20745,39245:20737,39246:20738,39247:20758,39248:20757,39249:20756,39250:20762,39251:20769,39252:20794,39253:20791,39254:20796,39255:20795,39256:20799,39257:20800,39258:20818,39259:20812,39260:20820,39261:20834,39262:31480,39263:20841,39264:20842,39265:20846,39266:20864,39267:20866,39268:22232,39269:20876,39270:20873,39271:20879,39272:20881,39273:20883,39274:20885,39275:20886,39276:20900,39277:20902,39278:20898,39279:20905,39280:20906,39281:20907,39282:20915,39283:20913,39284:20914,39285:20912,39286:20917,39287:20925,39288:20933,39289:20937,39290:20955,39291:20960,39292:34389,39293:20969,39294:20973,39296:20976,39297:20981,39298:20990,39299:20996,39300:21003,39301:21012,39302:21006,39303:21031,39304:21034,39305:21038,39306:21043,39307:21049,39308:21071,39309:21060,39310:21067,39311:21068,39312:21086,39313:21076,39314:21098,39315:21108,39316:21097,39317:21107,39318:21119,39319:21117,39320:21133,39321:21140,39322:21138,39323:21105,39324:21128,39325:21137,39326:36776,39327:36775,39328:21164,39329:21165,39330:21180,39331:21173,39332:21185,39333:21197,39334:21207,39335:21214,39336:21219,39337:21222,39338:39149,39339:21216,39340:21235,39341:21237,39342:21240,39343:21241,39344:21254,39345:21256,39346:30008,39347:21261,39348:21264,39349:21263,39350:21269,39351:21274,39352:21283,39353:21295,39354:21297,39355:21299,39356:21304,39357:21312,39358:21318,39359:21317,39360:19991,39361:21321,39362:21325,39363:20950,39364:21342,39365:21353,39366:21358,39367:22808,39368:21371,39369:21367,39370:21378,39371:21398,39372:21408,39373:21414,39374:21413,39375:21422,39376:21424,39377:21430,39378:21443,39379:31762,39380:38617,39381:21471,39382:26364,39383:29166,39384:21486,39385:21480,39386:21485,39387:21498,39388:21505,39389:21565,39390:21568,39391:21548,39392:21549,39393:21564,39394:21550,39395:21558,39396:21545,39397:21533,39398:21582,39399:21647,39400:21621,39401:21646,39402:21599,39403:21617,39404:21623,39405:21616,39406:21650,39407:21627,39408:21632,39409:21622,39410:21636,39411:21648,39412:21638,39413:21703,39414:21666,39415:21688,39416:21669,39417:21676,39418:21700,39419:21704,39420:21672,39488:21675,39489:21698,39490:21668,39491:21694,39492:21692,39493:21720,39494:21733,39495:21734,39496:21775,39497:21780,39498:21757,39499:21742,39500:21741,39501:21754,39502:21730,39503:21817,39504:21824,39505:21859,39506:21836,39507:21806,39508:21852,39509:21829,39510:21846,39511:21847,39512:21816,39513:21811,39514:21853,39515:21913,39516:21888,39517:21679,39518:21898,39519:21919,39520:21883,39521:21886,39522:21912,39523:21918,39524:21934,39525:21884,39526:21891,39527:21929,39528:21895,39529:21928,39530:21978,39531:21957,39532:21983,39533:21956,39534:21980,39535:21988,39536:21972,39537:22036,39538:22007,39539:22038,39540:22014,39541:22013,39542:22043,39543:22009,39544:22094,39545:22096,39546:29151,39547:22068,39548:22070,39549:22066,39550:22072,39552:22123,39553:22116,39554:22063,39555:22124,39556:22122,39557:22150,39558:22144,39559:22154,39560:22176,39561:22164,39562:22159,39563:22181,39564:22190,39565:22198,39566:22196,39567:22210,39568:22204,39569:22209,39570:22211,39571:22208,39572:22216,39573:22222,39574:22225,39575:22227,39576:22231,39577:22254,39578:22265,39579:22272,39580:22271,39581:22276,39582:22281,39583:22280,39584:22283,39585:22285,39586:22291,39587:22296,39588:22294,39589:21959,39590:22300,39591:22310,39592:22327,39593:22328,39594:22350,39595:22331,39596:22336,39597:22351,39598:22377,39599:22464,39600:22408,39601:22369,39602:22399,39603:22409,39604:22419,39605:22432,39606:22451,39607:22436,39608:22442,39609:22448,39610:22467,39611:22470,39612:22484,39613:22482,39614:22483,39615:22538,39616:22486,39617:22499,39618:22539,39619:22553,39620:22557,39621:22642,39622:22561,39623:22626,39624:22603,39625:22640,39626:27584,39627:22610,39628:22589,39629:22649,39630:22661,39631:22713,39632:22687,39633:22699,39634:22714,39635:22750,39636:22715,39637:22712,39638:22702,39639:22725,39640:22739,39641:22737,39642:22743,39643:22745,39644:22744,39645:22757,39646:22748,39647:22756,39648:22751,39649:22767,39650:22778,39651:22777,39652:22779,39653:22780,39654:22781,39655:22786,39656:22794,39657:22800,39658:22811,39659:26790,39660:22821,39661:22828,39662:22829,39663:22834,39664:22840,39665:22846,39666:31442,39667:22869,39668:22864,39669:22862,39670:22874,39671:22872,39672:22882,39673:22880,39674:22887,39675:22892,39676:22889,39744:22904,39745:22913,39746:22941,39747:20318,39748:20395,39749:22947,39750:22962,39751:22982,39752:23016,39753:23004,39754:22925,39755:23001,39756:23002,39757:23077,39758:23071,39759:23057,39760:23068,39761:23049,39762:23066,39763:23104,39764:23148,39765:23113,39766:23093,39767:23094,39768:23138,39769:23146,39770:23194,39771:23228,39772:23230,39773:23243,39774:23234,39775:23229,39776:23267,39777:23255,39778:23270,39779:23273,39780:23254,39781:23290,39782:23291,39783:23308,39784:23307,39785:23318,39786:23346,39787:23248,39788:23338,39789:23350,39790:23358,39791:23363,39792:23365,39793:23360,39794:23377,39795:23381,39796:23386,39797:23387,39798:23397,39799:23401,39800:23408,39801:23411,39802:23413,39803:23416,39804:25992,39805:23418,39806:23424,39808:23427,39809:23462,39810:23480,39811:23491,39812:23495,39813:23497,39814:23508,39815:23504,39816:23524,39817:23526,39818:23522,39819:23518,39820:23525,39821:23531,39822:23536,39823:23542,39824:23539,39825:23557,39826:23559,39827:23560,39828:23565,39829:23571,39830:23584,39831:23586,39832:23592,39833:23608,39834:23609,39835:23617,39836:23622,39837:23630,39838:23635,39839:23632,39840:23631,39841:23409,39842:23660,39843:23662,39844:20066,39845:23670,39846:23673,39847:23692,39848:23697,39849:23700,39850:22939,39851:23723,39852:23739,39853:23734,39854:23740,39855:23735,39856:23749,39857:23742,39858:23751,39859:23769,39860:23785,39861:23805,39862:23802,39863:23789,39864:23948,39865:23786,39866:23819,39867:23829,39868:23831,39869:23900,39870:23839,39871:23835,39872:23825,39873:23828,39874:23842,39875:23834,39876:23833,39877:23832,39878:23884,39879:23890,39880:23886,39881:23883,39882:23916,39883:23923,39884:23926,39885:23943,39886:23940,39887:23938,39888:23970,39889:23965,39890:23980,39891:23982,39892:23997,39893:23952,39894:23991,39895:23996,39896:24009,39897:24013,39898:24019,39899:24018,39900:24022,39901:24027,39902:24043,39903:24050,39904:24053,39905:24075,39906:24090,39907:24089,39908:24081,39909:24091,39910:24118,39911:24119,39912:24132,39913:24131,39914:24128,39915:24142,39916:24151,39917:24148,39918:24159,39919:24162,39920:24164,39921:24135,39922:24181,39923:24182,39924:24186,39925:40636,39926:24191,39927:24224,39928:24257,39929:24258,39930:24264,39931:24272,39932:24271,4e4:24278,40001:24291,40002:24285,40003:24282,40004:24283,40005:24290,40006:24289,40007:24296,40008:24297,40009:24300,40010:24305,40011:24307,40012:24304,40013:24308,40014:24312,40015:24318,40016:24323,40017:24329,40018:24413,40019:24412,40020:24331,40021:24337,40022:24342,40023:24361,40024:24365,40025:24376,40026:24385,40027:24392,40028:24396,40029:24398,40030:24367,40031:24401,40032:24406,40033:24407,40034:24409,40035:24417,40036:24429,40037:24435,40038:24439,40039:24451,40040:24450,40041:24447,40042:24458,40043:24456,40044:24465,40045:24455,40046:24478,40047:24473,40048:24472,40049:24480,40050:24488,40051:24493,40052:24508,40053:24534,40054:24571,40055:24548,40056:24568,40057:24561,40058:24541,40059:24755,40060:24575,40061:24609,40062:24672,40064:24601,40065:24592,40066:24617,40067:24590,40068:24625,40069:24603,40070:24597,40071:24619,40072:24614,40073:24591,40074:24634,40075:24666,40076:24641,40077:24682,40078:24695,40079:24671,40080:24650,40081:24646,40082:24653,40083:24675,40084:24643,40085:24676,40086:24642,40087:24684,40088:24683,40089:24665,40090:24705,40091:24717,40092:24807,40093:24707,40094:24730,40095:24708,40096:24731,40097:24726,40098:24727,40099:24722,40100:24743,40101:24715,40102:24801,40103:24760,40104:24800,40105:24787,40106:24756,40107:24560,40108:24765,40109:24774,40110:24757,40111:24792,40112:24909,40113:24853,40114:24838,40115:24822,40116:24823,40117:24832,40118:24820,40119:24826,40120:24835,40121:24865,40122:24827,40123:24817,40124:24845,40125:24846,40126:24903,40127:24894,40128:24872,40129:24871,40130:24906,40131:24895,40132:24892,40133:24876,40134:24884,40135:24893,40136:24898,40137:24900,40138:24947,40139:24951,40140:24920,40141:24921,40142:24922,40143:24939,40144:24948,40145:24943,40146:24933,40147:24945,40148:24927,40149:24925,40150:24915,40151:24949,40152:24985,40153:24982,40154:24967,40155:25004,40156:24980,40157:24986,40158:24970,40159:24977,40160:25003,40161:25006,40162:25036,40163:25034,40164:25033,40165:25079,40166:25032,40167:25027,40168:25030,40169:25018,40170:25035,40171:32633,40172:25037,40173:25062,40174:25059,40175:25078,40176:25082,40177:25076,40178:25087,40179:25085,40180:25084,40181:25086,40182:25088,40183:25096,40184:25097,40185:25101,40186:25100,40187:25108,40188:25115,40256:25118,40257:25121,40258:25130,40259:25134,40260:25136,40261:25138,40262:25139,40263:25153,40264:25166,40265:25182,40266:25187,40267:25179,40268:25184,40269:25192,40270:25212,40271:25218,40272:25225,40273:25214,40274:25234,40275:25235,40276:25238,40277:25300,40278:25219,40279:25236,40280:25303,40281:25297,40282:25275,40283:25295,40284:25343,40285:25286,40286:25812,40287:25288,40288:25308,40289:25292,40290:25290,40291:25282,40292:25287,40293:25243,40294:25289,40295:25356,40296:25326,40297:25329,40298:25383,40299:25346,40300:25352,40301:25327,40302:25333,40303:25424,40304:25406,40305:25421,40306:25628,40307:25423,40308:25494,40309:25486,40310:25472,40311:25515,40312:25462,40313:25507,40314:25487,40315:25481,40316:25503,40317:25525,40318:25451,40320:25449,40321:25534,40322:25577,40323:25536,40324:25542,40325:25571,40326:25545,40327:25554,40328:25590,40329:25540,40330:25622,40331:25652,40332:25606,40333:25619,40334:25638,40335:25654,40336:25885,40337:25623,40338:25640,40339:25615,40340:25703,40341:25711,40342:25718,40343:25678,40344:25898,40345:25749,40346:25747,40347:25765,40348:25769,40349:25736,40350:25788,40351:25818,40352:25810,40353:25797,40354:25799,40355:25787,40356:25816,40357:25794,40358:25841,40359:25831,40360:33289,40361:25824,40362:25825,40363:25260,40364:25827,40365:25839,40366:25900,40367:25846,40368:25844,40369:25842,40370:25850,40371:25856,40372:25853,40373:25880,40374:25884,40375:25861,40376:25892,40377:25891,40378:25899,40379:25908,40380:25909,40381:25911,40382:25910,40383:25912,40384:30027,40385:25928,40386:25942,40387:25941,40388:25933,40389:25944,40390:25950,40391:25949,40392:25970,40393:25976,40394:25986,40395:25987,40396:35722,40397:26011,40398:26015,40399:26027,40400:26039,40401:26051,40402:26054,40403:26049,40404:26052,40405:26060,40406:26066,40407:26075,40408:26073,40409:26080,40410:26081,40411:26097,40412:26482,40413:26122,40414:26115,40415:26107,40416:26483,40417:26165,40418:26166,40419:26164,40420:26140,40421:26191,40422:26180,40423:26185,40424:26177,40425:26206,40426:26205,40427:26212,40428:26215,40429:26216,40430:26207,40431:26210,40432:26224,40433:26243,40434:26248,40435:26254,40436:26249,40437:26244,40438:26264,40439:26269,40440:26305,40441:26297,40442:26313,40443:26302,40444:26300,40512:26308,40513:26296,40514:26326,40515:26330,40516:26336,40517:26175,40518:26342,40519:26345,40520:26352,40521:26357,40522:26359,40523:26383,40524:26390,40525:26398,40526:26406,40527:26407,40528:38712,40529:26414,40530:26431,40531:26422,40532:26433,40533:26424,40534:26423,40535:26438,40536:26462,40537:26464,40538:26457,40539:26467,40540:26468,40541:26505,40542:26480,40543:26537,40544:26492,40545:26474,40546:26508,40547:26507,40548:26534,40549:26529,40550:26501,40551:26551,40552:26607,40553:26548,40554:26604,40555:26547,40556:26601,40557:26552,40558:26596,40559:26590,40560:26589,40561:26594,40562:26606,40563:26553,40564:26574,40565:26566,40566:26599,40567:27292,40568:26654,40569:26694,40570:26665,40571:26688,40572:26701,40573:26674,40574:26702,40576:26803,40577:26667,40578:26713,40579:26723,40580:26743,40581:26751,40582:26783,40583:26767,40584:26797,40585:26772,40586:26781,40587:26779,40588:26755,40589:27310,40590:26809,40591:26740,40592:26805,40593:26784,40594:26810,40595:26895,40596:26765,40597:26750,40598:26881,40599:26826,40600:26888,40601:26840,40602:26914,40603:26918,40604:26849,40605:26892,40606:26829,40607:26836,40608:26855,40609:26837,40610:26934,40611:26898,40612:26884,40613:26839,40614:26851,40615:26917,40616:26873,40617:26848,40618:26863,40619:26920,40620:26922,40621:26906,40622:26915,40623:26913,40624:26822,40625:27001,40626:26999,40627:26972,40628:27e3,40629:26987,40630:26964,40631:27006,40632:26990,40633:26937,40634:26996,40635:26941,40636:26969,40637:26928,40638:26977,40639:26974,40640:26973,40641:27009,40642:26986,40643:27058,40644:27054,40645:27088,40646:27071,40647:27073,40648:27091,40649:27070,40650:27086,40651:23528,40652:27082,40653:27101,40654:27067,40655:27075,40656:27047,40657:27182,40658:27025,40659:27040,40660:27036,40661:27029,40662:27060,40663:27102,40664:27112,40665:27138,40666:27163,40667:27135,40668:27402,40669:27129,40670:27122,40671:27111,40672:27141,40673:27057,40674:27166,40675:27117,40676:27156,40677:27115,40678:27146,40679:27154,40680:27329,40681:27171,40682:27155,40683:27204,40684:27148,40685:27250,40686:27190,40687:27256,40688:27207,40689:27234,40690:27225,40691:27238,40692:27208,40693:27192,40694:27170,40695:27280,40696:27277,40697:27296,40698:27268,40699:27298,40700:27299,40768:27287,40769:34327,40770:27323,40771:27331,40772:27330,40773:27320,40774:27315,40775:27308,40776:27358,40777:27345,40778:27359,40779:27306,40780:27354,40781:27370,40782:27387,40783:27397,40784:34326,40785:27386,40786:27410,40787:27414,40788:39729,40789:27423,40790:27448,40791:27447,40792:30428,40793:27449,40794:39150,40795:27463,40796:27459,40797:27465,40798:27472,40799:27481,40800:27476,40801:27483,40802:27487,40803:27489,40804:27512,40805:27513,40806:27519,40807:27520,40808:27524,40809:27523,40810:27533,40811:27544,40812:27541,40813:27550,40814:27556,40815:27562,40816:27563,40817:27567,40818:27570,40819:27569,40820:27571,40821:27575,40822:27580,40823:27590,40824:27595,40825:27603,40826:27615,40827:27628,40828:27627,40829:27635,40830:27631,40832:40638,40833:27656,40834:27667,40835:27668,40836:27675,40837:27684,40838:27683,40839:27742,40840:27733,40841:27746,40842:27754,40843:27778,40844:27789,40845:27802,40846:27777,40847:27803,40848:27774,40849:27752,40850:27763,40851:27794,40852:27792,40853:27844,40854:27889,40855:27859,40856:27837,40857:27863,40858:27845,40859:27869,40860:27822,40861:27825,40862:27838,40863:27834,40864:27867,40865:27887,40866:27865,40867:27882,40868:27935,40869:34893,40870:27958,40871:27947,40872:27965,40873:27960,40874:27929,40875:27957,40876:27955,40877:27922,40878:27916,40879:28003,40880:28051,40881:28004,40882:27994,40883:28025,40884:27993,40885:28046,40886:28053,40887:28644,40888:28037,40889:28153,40890:28181,40891:28170,40892:28085,40893:28103,40894:28134,40895:28088,40896:28102,40897:28140,40898:28126,40899:28108,40900:28136,40901:28114,40902:28101,40903:28154,40904:28121,40905:28132,40906:28117,40907:28138,40908:28142,40909:28205,40910:28270,40911:28206,40912:28185,40913:28274,40914:28255,40915:28222,40916:28195,40917:28267,40918:28203,40919:28278,40920:28237,40921:28191,40922:28227,40923:28218,40924:28238,40925:28196,40926:28415,40927:28189,40928:28216,40929:28290,40930:28330,40931:28312,40932:28361,40933:28343,40934:28371,40935:28349,40936:28335,40937:28356,40938:28338,40939:28372,40940:28373,40941:28303,40942:28325,40943:28354,40944:28319,40945:28481,40946:28433,40947:28748,40948:28396,40949:28408,40950:28414,40951:28479,40952:28402,40953:28465,40954:28399,40955:28466,40956:28364,161:65377,162:65378,163:65379,164:65380,165:65381,166:65382,167:65383,168:65384,169:65385,170:65386,171:65387,172:65388,173:65389,174:65390,175:65391,176:65392,177:65393,178:65394,179:65395,180:65396,181:65397,182:65398,183:65399,184:65400,185:65401,186:65402,187:65403,188:65404,189:65405,190:65406,191:65407,192:65408,193:65409,194:65410,195:65411,196:65412,197:65413,198:65414,199:65415,200:65416,201:65417,202:65418,203:65419,204:65420,205:65421,206:65422,207:65423,208:65424,209:65425,210:65426,211:65427,212:65428,213:65429,214:65430,215:65431,216:65432,217:65433,218:65434,219:65435,220:65436,221:65437,222:65438,223:65439,57408:28478,57409:28435,57410:28407,57411:28550,57412:28538,57413:28536,57414:28545,57415:28544,57416:28527,57417:28507,57418:28659,57419:28525,57420:28546,57421:28540,57422:28504,57423:28558,57424:28561,57425:28610,57426:28518,57427:28595,57428:28579,57429:28577,57430:28580,57431:28601,57432:28614,57433:28586,57434:28639,57435:28629,57436:28652,57437:28628,57438:28632,57439:28657,57440:28654,57441:28635,57442:28681,57443:28683,57444:28666,57445:28689,57446:28673,57447:28687,57448:28670,57449:28699,57450:28698,57451:28532,57452:28701,57453:28696,57454:28703,57455:28720,57456:28734,57457:28722,57458:28753,57459:28771,57460:28825,57461:28818,57462:28847,57463:28913,57464:28844,57465:28856,57466:28851,57467:28846,57468:28895,57469:28875,57470:28893,57472:28889,57473:28937,57474:28925,57475:28956,57476:28953,57477:29029,57478:29013,57479:29064,57480:29030,57481:29026,57482:29004,57483:29014,57484:29036,57485:29071,57486:29179,57487:29060,57488:29077,57489:29096,57490:29100,57491:29143,57492:29113,57493:29118,57494:29138,57495:29129,57496:29140,57497:29134,57498:29152,57499:29164,57500:29159,57501:29173,57502:29180,57503:29177,57504:29183,57505:29197,57506:29200,57507:29211,57508:29224,57509:29229,57510:29228,57511:29232,57512:29234,57513:29243,57514:29244,57515:29247,57516:29248,57517:29254,57518:29259,57519:29272,57520:29300,57521:29310,57522:29314,57523:29313,57524:29319,57525:29330,57526:29334,57527:29346,57528:29351,57529:29369,57530:29362,57531:29379,57532:29382,57533:29380,57534:29390,57535:29394,57536:29410,57537:29408,57538:29409,57539:29433,57540:29431,57541:20495,57542:29463,57543:29450,57544:29468,57545:29462,57546:29469,57547:29492,57548:29487,57549:29481,57550:29477,57551:29502,57552:29518,57553:29519,57554:40664,57555:29527,57556:29546,57557:29544,57558:29552,57559:29560,57560:29557,57561:29563,57562:29562,57563:29640,57564:29619,57565:29646,57566:29627,57567:29632,57568:29669,57569:29678,57570:29662,57571:29858,57572:29701,57573:29807,57574:29733,57575:29688,57576:29746,57577:29754,57578:29781,57579:29759,57580:29791,57581:29785,57582:29761,57583:29788,57584:29801,57585:29808,57586:29795,57587:29802,57588:29814,57589:29822,57590:29835,57591:29854,57592:29863,57593:29898,57594:29903,57595:29908,57596:29681,57664:29920,57665:29923,57666:29927,57667:29929,57668:29934,57669:29938,57670:29936,57671:29937,57672:29944,57673:29943,57674:29956,57675:29955,57676:29957,57677:29964,57678:29966,57679:29965,57680:29973,57681:29971,57682:29982,57683:29990,57684:29996,57685:30012,57686:30020,57687:30029,57688:30026,57689:30025,57690:30043,57691:30022,57692:30042,57693:30057,57694:30052,57695:30055,57696:30059,57697:30061,57698:30072,57699:30070,57700:30086,57701:30087,57702:30068,57703:30090,57704:30089,57705:30082,57706:30100,57707:30106,57708:30109,57709:30117,57710:30115,57711:30146,57712:30131,57713:30147,57714:30133,57715:30141,57716:30136,57717:30140,57718:30129,57719:30157,57720:30154,57721:30162,57722:30169,57723:30179,57724:30174,57725:30206,57726:30207,57728:30204,57729:30209,57730:30192,57731:30202,57732:30194,57733:30195,57734:30219,57735:30221,57736:30217,57737:30239,57738:30247,57739:30240,57740:30241,57741:30242,57742:30244,57743:30260,57744:30256,57745:30267,57746:30279,57747:30280,57748:30278,57749:30300,57750:30296,57751:30305,57752:30306,57753:30312,57754:30313,57755:30314,57756:30311,57757:30316,57758:30320,57759:30322,57760:30326,57761:30328,57762:30332,57763:30336,57764:30339,57765:30344,57766:30347,57767:30350,57768:30358,57769:30355,57770:30361,57771:30362,57772:30384,57773:30388,57774:30392,57775:30393,57776:30394,57777:30402,57778:30413,57779:30422,57780:30418,57781:30430,57782:30433,57783:30437,57784:30439,57785:30442,57786:34351,57787:30459,57788:30472,57789:30471,57790:30468,57791:30505,57792:30500,57793:30494,57794:30501,57795:30502,57796:30491,57797:30519,57798:30520,57799:30535,57800:30554,57801:30568,57802:30571,57803:30555,57804:30565,57805:30591,57806:30590,57807:30585,57808:30606,57809:30603,57810:30609,57811:30624,57812:30622,57813:30640,57814:30646,57815:30649,57816:30655,57817:30652,57818:30653,57819:30651,57820:30663,57821:30669,57822:30679,57823:30682,57824:30684,57825:30691,57826:30702,57827:30716,57828:30732,57829:30738,57830:31014,57831:30752,57832:31018,57833:30789,57834:30862,57835:30836,57836:30854,57837:30844,57838:30874,57839:30860,57840:30883,57841:30901,57842:30890,57843:30895,57844:30929,57845:30918,57846:30923,57847:30932,57848:30910,57849:30908,57850:30917,57851:30922,57852:30956,57920:30951,57921:30938,57922:30973,57923:30964,57924:30983,57925:30994,57926:30993,57927:31001,57928:31020,57929:31019,57930:31040,57931:31072,57932:31063,57933:31071,57934:31066,57935:31061,57936:31059,57937:31098,57938:31103,57939:31114,57940:31133,57941:31143,57942:40779,57943:31146,57944:31150,57945:31155,57946:31161,57947:31162,57948:31177,57949:31189,57950:31207,57951:31212,57952:31201,57953:31203,57954:31240,57955:31245,57956:31256,57957:31257,57958:31264,57959:31263,57960:31104,57961:31281,57962:31291,57963:31294,57964:31287,57965:31299,57966:31319,57967:31305,57968:31329,57969:31330,57970:31337,57971:40861,57972:31344,57973:31353,57974:31357,57975:31368,57976:31383,57977:31381,57978:31384,57979:31382,57980:31401,57981:31432,57982:31408,57984:31414,57985:31429,57986:31428,57987:31423,57988:36995,57989:31431,57990:31434,57991:31437,57992:31439,57993:31445,57994:31443,57995:31449,57996:31450,57997:31453,57998:31457,57999:31458,58e3:31462,58001:31469,58002:31472,58003:31490,58004:31503,58005:31498,58006:31494,58007:31539,58008:31512,58009:31513,58010:31518,58011:31541,58012:31528,58013:31542,58014:31568,58015:31610,58016:31492,58017:31565,58018:31499,58019:31564,58020:31557,58021:31605,58022:31589,58023:31604,58024:31591,58025:31600,58026:31601,58027:31596,58028:31598,58029:31645,58030:31640,58031:31647,58032:31629,58033:31644,58034:31642,58035:31627,58036:31634,58037:31631,58038:31581,58039:31641,58040:31691,58041:31681,58042:31692,58043:31695,58044:31668,58045:31686,58046:31709,58047:31721,58048:31761,58049:31764,58050:31718,58051:31717,58052:31840,58053:31744,58054:31751,58055:31763,58056:31731,58057:31735,58058:31767,58059:31757,58060:31734,58061:31779,58062:31783,58063:31786,58064:31775,58065:31799,58066:31787,58067:31805,58068:31820,58069:31811,58070:31828,58071:31823,58072:31808,58073:31824,58074:31832,58075:31839,58076:31844,58077:31830,58078:31845,58079:31852,58080:31861,58081:31875,58082:31888,58083:31908,58084:31917,58085:31906,58086:31915,58087:31905,58088:31912,58089:31923,58090:31922,58091:31921,58092:31918,58093:31929,58094:31933,58095:31936,58096:31941,58097:31938,58098:31960,58099:31954,58100:31964,58101:31970,58102:39739,58103:31983,58104:31986,58105:31988,58106:31990,58107:31994,58108:32006,58176:32002,58177:32028,58178:32021,58179:32010,58180:32069,58181:32075,58182:32046,58183:32050,58184:32063,58185:32053,58186:32070,58187:32115,58188:32086,58189:32078,58190:32114,58191:32104,58192:32110,58193:32079,58194:32099,58195:32147,58196:32137,58197:32091,58198:32143,58199:32125,58200:32155,58201:32186,58202:32174,58203:32163,58204:32181,58205:32199,58206:32189,58207:32171,58208:32317,58209:32162,58210:32175,58211:32220,58212:32184,58213:32159,58214:32176,58215:32216,58216:32221,58217:32228,58218:32222,58219:32251,58220:32242,58221:32225,58222:32261,58223:32266,58224:32291,58225:32289,58226:32274,58227:32305,58228:32287,58229:32265,58230:32267,58231:32290,58232:32326,58233:32358,58234:32315,58235:32309,58236:32313,58237:32323,58238:32311,58240:32306,58241:32314,58242:32359,58243:32349,58244:32342,58245:32350,58246:32345,58247:32346,58248:32377,58249:32362,58250:32361,58251:32380,58252:32379,58253:32387,58254:32213,58255:32381,58256:36782,58257:32383,58258:32392,58259:32393,58260:32396,58261:32402,58262:32400,58263:32403,58264:32404,58265:32406,58266:32398,58267:32411,58268:32412,58269:32568,58270:32570,58271:32581,58272:32588,58273:32589,58274:32590,58275:32592,58276:32593,58277:32597,58278:32596,58279:32600,58280:32607,58281:32608,58282:32616,58283:32617,58284:32615,58285:32632,58286:32642,58287:32646,58288:32643,58289:32648,58290:32647,58291:32652,58292:32660,58293:32670,58294:32669,58295:32666,58296:32675,58297:32687,58298:32690,58299:32697,58300:32686,58301:32694,58302:32696,58303:35697,58304:32709,58305:32710,58306:32714,58307:32725,58308:32724,58309:32737,58310:32742,58311:32745,58312:32755,58313:32761,58314:39132,58315:32774,58316:32772,58317:32779,58318:32786,58319:32792,58320:32793,58321:32796,58322:32801,58323:32808,58324:32831,58325:32827,58326:32842,58327:32838,58328:32850,58329:32856,58330:32858,58331:32863,58332:32866,58333:32872,58334:32883,58335:32882,58336:32880,58337:32886,58338:32889,58339:32893,58340:32895,58341:32900,58342:32902,58343:32901,58344:32923,58345:32915,58346:32922,58347:32941,58348:20880,58349:32940,58350:32987,58351:32997,58352:32985,58353:32989,58354:32964,58355:32986,58356:32982,58357:33033,58358:33007,58359:33009,58360:33051,58361:33065,58362:33059,58363:33071,58364:33099,58432:38539,58433:33094,58434:33086,58435:33107,58436:33105,58437:33020,58438:33137,58439:33134,58440:33125,58441:33126,58442:33140,58443:33155,58444:33160,58445:33162,58446:33152,58447:33154,58448:33184,58449:33173,58450:33188,58451:33187,58452:33119,58453:33171,58454:33193,58455:33200,58456:33205,58457:33214,58458:33208,58459:33213,58460:33216,58461:33218,58462:33210,58463:33225,58464:33229,58465:33233,58466:33241,58467:33240,58468:33224,58469:33242,58470:33247,58471:33248,58472:33255,58473:33274,58474:33275,58475:33278,58476:33281,58477:33282,58478:33285,58479:33287,58480:33290,58481:33293,58482:33296,58483:33302,58484:33321,58485:33323,58486:33336,58487:33331,58488:33344,58489:33369,58490:33368,58491:33373,58492:33370,58493:33375,58494:33380,58496:33378,58497:33384,58498:33386,58499:33387,58500:33326,58501:33393,58502:33399,58503:33400,58504:33406,58505:33421,58506:33426,58507:33451,58508:33439,58509:33467,58510:33452,58511:33505,58512:33507,58513:33503,58514:33490,58515:33524,58516:33523,58517:33530,58518:33683,58519:33539,58520:33531,58521:33529,58522:33502,58523:33542,58524:33500,58525:33545,58526:33497,58527:33589,58528:33588,58529:33558,58530:33586,58531:33585,58532:33600,58533:33593,58534:33616,58535:33605,58536:33583,58537:33579,58538:33559,58539:33560,58540:33669,58541:33690,58542:33706,58543:33695,58544:33698,58545:33686,58546:33571,58547:33678,58548:33671,58549:33674,58550:33660,58551:33717,58552:33651,58553:33653,58554:33696,58555:33673,58556:33704,58557:33780,58558:33811,58559:33771,58560:33742,58561:33789,58562:33795,58563:33752,58564:33803,58565:33729,58566:33783,58567:33799,58568:33760,58569:33778,58570:33805,58571:33826,58572:33824,58573:33725,58574:33848,58575:34054,58576:33787,58577:33901,58578:33834,58579:33852,58580:34138,58581:33924,58582:33911,58583:33899,58584:33965,58585:33902,58586:33922,58587:33897,58588:33862,58589:33836,58590:33903,58591:33913,58592:33845,58593:33994,58594:33890,58595:33977,58596:33983,58597:33951,58598:34009,58599:33997,58600:33979,58601:34010,58602:34e3,58603:33985,58604:33990,58605:34006,58606:33953,58607:34081,58608:34047,58609:34036,58610:34071,58611:34072,58612:34092,58613:34079,58614:34069,58615:34068,58616:34044,58617:34112,58618:34147,58619:34136,58620:34120,58688:34113,58689:34306,58690:34123,58691:34133,58692:34176,58693:34212,58694:34184,58695:34193,58696:34186,58697:34216,58698:34157,58699:34196,58700:34203,58701:34282,58702:34183,58703:34204,58704:34167,58705:34174,58706:34192,58707:34249,58708:34234,58709:34255,58710:34233,58711:34256,58712:34261,58713:34269,58714:34277,58715:34268,58716:34297,58717:34314,58718:34323,58719:34315,58720:34302,58721:34298,58722:34310,58723:34338,58724:34330,58725:34352,58726:34367,58727:34381,58728:20053,58729:34388,58730:34399,58731:34407,58732:34417,58733:34451,58734:34467,58735:34473,58736:34474,58737:34443,58738:34444,58739:34486,58740:34479,58741:34500,58742:34502,58743:34480,58744:34505,58745:34851,58746:34475,58747:34516,58748:34526,58749:34537,58750:34540,58752:34527,58753:34523,58754:34543,58755:34578,58756:34566,58757:34568,58758:34560,58759:34563,58760:34555,58761:34577,58762:34569,58763:34573,58764:34553,58765:34570,58766:34612,58767:34623,58768:34615,58769:34619,58770:34597,58771:34601,58772:34586,58773:34656,58774:34655,58775:34680,58776:34636,58777:34638,58778:34676,58779:34647,58780:34664,58781:34670,58782:34649,58783:34643,58784:34659,58785:34666,58786:34821,58787:34722,58788:34719,58789:34690,58790:34735,58791:34763,58792:34749,58793:34752,58794:34768,58795:38614,58796:34731,58797:34756,58798:34739,58799:34759,58800:34758,58801:34747,58802:34799,58803:34802,58804:34784,58805:34831,58806:34829,58807:34814,58808:34806,58809:34807,58810:34830,58811:34770,58812:34833,58813:34838,58814:34837,58815:34850,58816:34849,58817:34865,58818:34870,58819:34873,58820:34855,58821:34875,58822:34884,58823:34882,58824:34898,58825:34905,58826:34910,58827:34914,58828:34923,58829:34945,58830:34942,58831:34974,58832:34933,58833:34941,58834:34997,58835:34930,58836:34946,58837:34967,58838:34962,58839:34990,58840:34969,58841:34978,58842:34957,58843:34980,58844:34992,58845:35007,58846:34993,58847:35011,58848:35012,58849:35028,58850:35032,58851:35033,58852:35037,58853:35065,58854:35074,58855:35068,58856:35060,58857:35048,58858:35058,58859:35076,58860:35084,58861:35082,58862:35091,58863:35139,58864:35102,58865:35109,58866:35114,58867:35115,58868:35137,58869:35140,58870:35131,58871:35126,58872:35128,58873:35148,58874:35101,58875:35168,58876:35166,58944:35174,58945:35172,58946:35181,58947:35178,58948:35183,58949:35188,58950:35191,58951:35198,58952:35203,58953:35208,58954:35210,58955:35219,58956:35224,58957:35233,58958:35241,58959:35238,58960:35244,58961:35247,58962:35250,58963:35258,58964:35261,58965:35263,58966:35264,58967:35290,58968:35292,58969:35293,58970:35303,58971:35316,58972:35320,58973:35331,58974:35350,58975:35344,58976:35340,58977:35355,58978:35357,58979:35365,58980:35382,58981:35393,58982:35419,58983:35410,58984:35398,58985:35400,58986:35452,58987:35437,58988:35436,58989:35426,58990:35461,58991:35458,58992:35460,58993:35496,58994:35489,58995:35473,58996:35493,58997:35494,58998:35482,58999:35491,59e3:35524,59001:35533,59002:35522,59003:35546,59004:35563,59005:35571,59006:35559,59008:35556,59009:35569,59010:35604,59011:35552,59012:35554,59013:35575,59014:35550,59015:35547,59016:35596,59017:35591,59018:35610,59019:35553,59020:35606,59021:35600,59022:35607,59023:35616,59024:35635,59025:38827,59026:35622,59027:35627,59028:35646,59029:35624,59030:35649,59031:35660,59032:35663,59033:35662,59034:35657,59035:35670,59036:35675,59037:35674,59038:35691,59039:35679,59040:35692,59041:35695,59042:35700,59043:35709,59044:35712,59045:35724,59046:35726,59047:35730,59048:35731,59049:35734,59050:35737,59051:35738,59052:35898,59053:35905,59054:35903,59055:35912,59056:35916,59057:35918,59058:35920,59059:35925,59060:35938,59061:35948,59062:35960,59063:35962,59064:35970,59065:35977,59066:35973,59067:35978,59068:35981,59069:35982,59070:35988,59071:35964,59072:35992,59073:25117,59074:36013,59075:36010,59076:36029,59077:36018,59078:36019,59079:36014,59080:36022,59081:36040,59082:36033,59083:36068,59084:36067,59085:36058,59086:36093,59087:36090,59088:36091,59089:36100,59090:36101,59091:36106,59092:36103,59093:36111,59094:36109,59095:36112,59096:40782,59097:36115,59098:36045,59099:36116,59100:36118,59101:36199,59102:36205,59103:36209,59104:36211,59105:36225,59106:36249,59107:36290,59108:36286,59109:36282,59110:36303,59111:36314,59112:36310,59113:36300,59114:36315,59115:36299,59116:36330,59117:36331,59118:36319,59119:36323,59120:36348,59121:36360,59122:36361,59123:36351,59124:36381,59125:36382,59126:36368,59127:36383,59128:36418,59129:36405,59130:36400,59131:36404,59132:36426,59200:36423,59201:36425,59202:36428,59203:36432,59204:36424,59205:36441,59206:36452,59207:36448,59208:36394,59209:36451,59210:36437,59211:36470,59212:36466,59213:36476,59214:36481,59215:36487,59216:36485,59217:36484,59218:36491,59219:36490,59220:36499,59221:36497,59222:36500,59223:36505,59224:36522,59225:36513,59226:36524,59227:36528,59228:36550,59229:36529,59230:36542,59231:36549,59232:36552,59233:36555,59234:36571,59235:36579,59236:36604,59237:36603,59238:36587,59239:36606,59240:36618,59241:36613,59242:36629,59243:36626,59244:36633,59245:36627,59246:36636,59247:36639,59248:36635,59249:36620,59250:36646,59251:36659,59252:36667,59253:36665,59254:36677,59255:36674,59256:36670,59257:36684,59258:36681,59259:36678,59260:36686,59261:36695,59262:36700,59264:36706,59265:36707,59266:36708,59267:36764,59268:36767,59269:36771,59270:36781,59271:36783,59272:36791,59273:36826,59274:36837,59275:36834,59276:36842,59277:36847,59278:36999,59279:36852,59280:36869,59281:36857,59282:36858,59283:36881,59284:36885,59285:36897,59286:36877,59287:36894,59288:36886,59289:36875,59290:36903,59291:36918,59292:36917,59293:36921,59294:36856,59295:36943,59296:36944,59297:36945,59298:36946,59299:36878,59300:36937,59301:36926,59302:36950,59303:36952,59304:36958,59305:36968,59306:36975,59307:36982,59308:38568,59309:36978,59310:36994,59311:36989,59312:36993,59313:36992,59314:37002,59315:37001,59316:37007,59317:37032,59318:37039,59319:37041,59320:37045,59321:37090,59322:37092,59323:25160,59324:37083,59325:37122,59326:37138,59327:37145,59328:37170,59329:37168,59330:37194,59331:37206,59332:37208,59333:37219,59334:37221,59335:37225,59336:37235,59337:37234,59338:37259,59339:37257,59340:37250,59341:37282,59342:37291,59343:37295,59344:37290,59345:37301,59346:37300,59347:37306,59348:37312,59349:37313,59350:37321,59351:37323,59352:37328,59353:37334,59354:37343,59355:37345,59356:37339,59357:37372,59358:37365,59359:37366,59360:37406,59361:37375,59362:37396,59363:37420,59364:37397,59365:37393,59366:37470,59367:37463,59368:37445,59369:37449,59370:37476,59371:37448,59372:37525,59373:37439,59374:37451,59375:37456,59376:37532,59377:37526,59378:37523,59379:37531,59380:37466,59381:37583,59382:37561,59383:37559,59384:37609,59385:37647,59386:37626,59387:37700,59388:37678,59456:37657,59457:37666,59458:37658,59459:37667,59460:37690,59461:37685,59462:37691,59463:37724,59464:37728,59465:37756,59466:37742,59467:37718,59468:37808,59469:37804,59470:37805,59471:37780,59472:37817,59473:37846,59474:37847,59475:37864,59476:37861,59477:37848,59478:37827,59479:37853,59480:37840,59481:37832,59482:37860,59483:37914,59484:37908,59485:37907,59486:37891,59487:37895,59488:37904,59489:37942,59490:37931,59491:37941,59492:37921,59493:37946,59494:37953,59495:37970,59496:37956,59497:37979,59498:37984,59499:37986,59500:37982,59501:37994,59502:37417,59503:38e3,59504:38005,59505:38007,59506:38013,59507:37978,59508:38012,59509:38014,59510:38017,59511:38015,59512:38274,59513:38279,59514:38282,59515:38292,59516:38294,59517:38296,59518:38297,59520:38304,59521:38312,59522:38311,59523:38317,59524:38332,59525:38331,59526:38329,59527:38334,59528:38346,59529:28662,59530:38339,59531:38349,59532:38348,59533:38357,59534:38356,59535:38358,59536:38364,59537:38369,59538:38373,59539:38370,59540:38433,59541:38440,59542:38446,59543:38447,59544:38466,59545:38476,59546:38479,59547:38475,59548:38519,59549:38492,59550:38494,59551:38493,59552:38495,59553:38502,59554:38514,59555:38508,59556:38541,59557:38552,59558:38549,59559:38551,59560:38570,59561:38567,59562:38577,59563:38578,59564:38576,59565:38580,59566:38582,59567:38584,59568:38585,59569:38606,59570:38603,59571:38601,59572:38605,59573:35149,59574:38620,59575:38669,59576:38613,59577:38649,59578:38660,59579:38662,59580:38664,59581:38675,59582:38670,59583:38673,59584:38671,59585:38678,59586:38681,59587:38692,59588:38698,59589:38704,59590:38713,59591:38717,59592:38718,59593:38724,59594:38726,59595:38728,59596:38722,59597:38729,59598:38748,59599:38752,59600:38756,59601:38758,59602:38760,59603:21202,59604:38763,59605:38769,59606:38777,59607:38789,59608:38780,59609:38785,59610:38778,59611:38790,59612:38795,59613:38799,59614:38800,59615:38812,59616:38824,59617:38822,59618:38819,59619:38835,59620:38836,59621:38851,59622:38854,59623:38856,59624:38859,59625:38876,59626:38893,59627:40783,59628:38898,59629:31455,59630:38902,59631:38901,59632:38927,59633:38924,59634:38968,59635:38948,59636:38945,59637:38967,59638:38973,59639:38982,59640:38991,59641:38987,59642:39019,59643:39023,59644:39024,59712:39025,59713:39028,59714:39027,59715:39082,59716:39087,59717:39089,59718:39094,59719:39108,59720:39107,59721:39110,59722:39145,59723:39147,59724:39171,59725:39177,59726:39186,59727:39188,59728:39192,59729:39201,59730:39197,59731:39198,59732:39204,59733:39200,59734:39212,59735:39214,59736:39229,59737:39230,59738:39234,59739:39241,59740:39237,59741:39248,59742:39243,59743:39249,59744:39250,59745:39244,59746:39253,59747:39319,59748:39320,59749:39333,59750:39341,59751:39342,59752:39356,59753:39391,59754:39387,59755:39389,59756:39384,59757:39377,59758:39405,59759:39406,59760:39409,59761:39410,59762:39419,59763:39416,59764:39425,59765:39439,59766:39429,59767:39394,59768:39449,59769:39467,59770:39479,59771:39493,59772:39490,59773:39488,59774:39491,59776:39486,59777:39509,59778:39501,59779:39515,59780:39511,59781:39519,59782:39522,59783:39525,59784:39524,59785:39529,59786:39531,59787:39530,59788:39597,59789:39600,59790:39612,59791:39616,59792:39631,59793:39633,59794:39635,59795:39636,59796:39646,59797:39647,59798:39650,59799:39651,59800:39654,59801:39663,59802:39659,59803:39662,59804:39668,59805:39665,59806:39671,59807:39675,59808:39686,59809:39704,59810:39706,59811:39711,59812:39714,59813:39715,59814:39717,59815:39719,59816:39720,59817:39721,59818:39722,59819:39726,59820:39727,59821:39730,59822:39748,59823:39747,59824:39759,59825:39757,59826:39758,59827:39761,59828:39768,59829:39796,59830:39827,59831:39811,59832:39825,59833:39830,59834:39831,59835:39839,59836:39840,59837:39848,59838:39860,59839:39872,59840:39882,59841:39865,59842:39878,59843:39887,59844:39889,59845:39890,59846:39907,59847:39906,59848:39908,59849:39892,59850:39905,59851:39994,59852:39922,59853:39921,59854:39920,59855:39957,59856:39956,59857:39945,59858:39955,59859:39948,59860:39942,59861:39944,59862:39954,59863:39946,59864:39940,59865:39982,59866:39963,59867:39973,59868:39972,59869:39969,59870:39984,59871:40007,59872:39986,59873:40006,59874:39998,59875:40026,59876:40032,59877:40039,59878:40054,59879:40056,59880:40167,59881:40172,59882:40176,59883:40201,59884:40200,59885:40171,59886:40195,59887:40198,59888:40234,59889:40230,59890:40367,59891:40227,59892:40223,59893:40260,59894:40213,59895:40210,59896:40257,59897:40255,59898:40254,59899:40262,59900:40264,59968:40285,59969:40286,59970:40292,59971:40273,59972:40272,59973:40281,59974:40306,59975:40329,59976:40327,59977:40363,59978:40303,59979:40314,59980:40346,59981:40356,59982:40361,59983:40370,59984:40388,59985:40385,59986:40379,59987:40376,59988:40378,59989:40390,59990:40399,59991:40386,59992:40409,59993:40403,59994:40440,59995:40422,59996:40429,59997:40431,59998:40445,59999:40474,6e4:40475,60001:40478,60002:40565,60003:40569,60004:40573,60005:40577,60006:40584,60007:40587,60008:40588,60009:40594,60010:40597,60011:40593,60012:40605,60013:40613,60014:40617,60015:40632,60016:40618,60017:40621,60018:38753,60019:40652,60020:40654,60021:40655,60022:40656,60023:40660,60024:40668,60025:40670,60026:40669,60027:40672,60028:40677,60029:40680,60030:40687,60032:40692,60033:40694,60034:40695,60035:40697,60036:40699,60037:40700,60038:40701,60039:40711,60040:40712,60041:30391,60042:40725,60043:40737,60044:40748,60045:40766,60046:40778,60047:40786,60048:40788,60049:40803,60050:40799,60051:40800,60052:40801,60053:40806,60054:40807,60055:40812,60056:40810,60057:40823,60058:40818,60059:40822,60060:40853,60061:40860,60062:40864,60063:22575,60064:27079,60065:36953,60066:29796,60067:20956,60068:29081}},function(o,e,r){"use strict";Object.defineProperty(e,"__esModule",{value:!0});var t=r(1),c=r(2);e.decode=function(o,e){var r=new Uint8ClampedArray(o.length);r.set(o);for(var s=new t.default(285,256,0),a=new c.default(s,r),n=new Uint8ClampedArray(e),d=!1,l=0;l<e;l++){var i=a.evaluateAt(s.exp(l+s.generatorBase));n[n.length-1-l]=i,0!==i&&(d=!0)}if(!d)return r;var B=new c.default(s,n),k=function(o,e,r,t){var c;e.degree()<r.degree()&&(e=(c=[r,e])[0],r=c[1]);for(var s=e,a=r,n=o.zero,d=o.one;a.degree()>=t/2;){var l=s,i=n;if(n=d,(s=a).isZero())return null;a=l;for(var B=o.zero,k=s.getCoefficient(s.degree()),u=o.inverse(k);a.degree()>=s.degree()&&!a.isZero();){var C=a.degree()-s.degree(),m=o.multiply(a.getCoefficient(a.degree()),u);B=B.addOrSubtract(o.buildMonomial(C,m)),a=a.addOrSubtract(s.multiplyByMonomial(C,m))}if(d=B.multiplyPoly(n).addOrSubtract(i),a.degree()>=s.degree())return null}var f=d.getCoefficient(0);if(0===f)return null;var w=o.inverse(f);return[d.multiply(w),a.multiply(w)]}(s,s.buildMonomial(e,1),B,e);if(null===k)return null;var u=function(o,e){var r=e.degree();if(1===r)return[e.getCoefficient(1)];for(var t=new Array(r),c=0,s=1;s<o.size&&c<r;s++)0===e.evaluateAt(s)&&(t[c]=o.inverse(s),c++);return c!==r?null:t}(s,k[0]);if(null==u)return null;for(var C=function(o,e,r){for(var c=r.length,s=new Array(c),a=0;a<c;a++){for(var n=o.inverse(r[a]),d=1,l=0;l<c;l++)a!==l&&(d=o.multiply(d,t.addOrSubtractGF(1,o.multiply(r[l],n))));s[a]=o.multiply(e.evaluateAt(n),o.inverse(d)),0!==o.generatorBase&&(s[a]=o.multiply(s[a],n))}return s}(s,k[1],u),m=0;m<u.length;m++){var f=r.length-1-s.log(u[m]);if(f<0)return null;r[f]=t.addOrSubtractGF(r[f],C[m])}return r}},function(o,e,r){"use strict";Object.defineProperty(e,"__esModule",{value:!0}),e.VERSIONS=[{infoBits:null,versionNumber:1,alignmentPatternCenters:[],errorCorrectionLevels:[{ecCodewordsPerBlock:7,ecBlocks:[{numBlocks:1,dataCodewordsPerBlock:19}]},{ecCodewordsPerBlock:10,ecBlocks:[{numBlocks:1,dataCodewordsPerBlock:16}]},{ecCodewordsPerBlock:13,ecBlocks:[{numBlocks:1,dataCodewordsPerBlock:13}]},{ecCodewordsPerBlock:17,ecBlocks:[{numBlocks:1,dataCodewordsPerBlock:9}]}]},{infoBits:null,versionNumber:2,alignmentPatternCenters:[6,18],errorCorrectionLevels:[{ecCodewordsPerBlock:10,ecBlocks:[{numBlocks:1,dataCodewordsPerBlock:34}]},{ecCodewordsPerBlock:16,ecBlocks:[{numBlocks:1,dataCodewordsPerBlock:28}]},{ecCodewordsPerBlock:22,ecBlocks:[{numBlocks:1,dataCodewordsPerBlock:22}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:1,dataCodewordsPerBlock:16}]}]},{infoBits:null,versionNumber:3,alignmentPatternCenters:[6,22],errorCorrectionLevels:[{ecCodewordsPerBlock:15,ecBlocks:[{numBlocks:1,dataCodewordsPerBlock:55}]},{ecCodewordsPerBlock:26,ecBlocks:[{numBlocks:1,dataCodewordsPerBlock:44}]},{ecCodewordsPerBlock:18,ecBlocks:[{numBlocks:2,dataCodewordsPerBlock:17}]},{ecCodewordsPerBlock:22,ecBlocks:[{numBlocks:2,dataCodewordsPerBlock:13}]}]},{infoBits:null,versionNumber:4,alignmentPatternCenters:[6,26],errorCorrectionLevels:[{ecCodewordsPerBlock:20,ecBlocks:[{numBlocks:1,dataCodewordsPerBlock:80}]},{ecCodewordsPerBlock:18,ecBlocks:[{numBlocks:2,dataCodewordsPerBlock:32}]},{ecCodewordsPerBlock:26,ecBlocks:[{numBlocks:2,dataCodewordsPerBlock:24}]},{ecCodewordsPerBlock:16,ecBlocks:[{numBlocks:4,dataCodewordsPerBlock:9}]}]},{infoBits:null,versionNumber:5,alignmentPatternCenters:[6,30],errorCorrectionLevels:[{ecCodewordsPerBlock:26,ecBlocks:[{numBlocks:1,dataCodewordsPerBlock:108}]},{ecCodewordsPerBlock:24,ecBlocks:[{numBlocks:2,dataCodewordsPerBlock:43}]},{ecCodewordsPerBlock:18,ecBlocks:[{numBlocks:2,dataCodewordsPerBlock:15},{numBlocks:2,dataCodewordsPerBlock:16}]},{ecCodewordsPerBlock:22,ecBlocks:[{numBlocks:2,dataCodewordsPerBlock:11},{numBlocks:2,dataCodewordsPerBlock:12}]}]},{infoBits:null,versionNumber:6,alignmentPatternCenters:[6,34],errorCorrectionLevels:[{ecCodewordsPerBlock:18,ecBlocks:[{numBlocks:2,dataCodewordsPerBlock:68}]},{ecCodewordsPerBlock:16,ecBlocks:[{numBlocks:4,dataCodewordsPerBlock:27}]},{ecCodewordsPerBlock:24,ecBlocks:[{numBlocks:4,dataCodewordsPerBlock:19}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:4,dataCodewordsPerBlock:15}]}]},{infoBits:31892,versionNumber:7,alignmentPatternCenters:[6,22,38],errorCorrectionLevels:[{ecCodewordsPerBlock:20,ecBlocks:[{numBlocks:2,dataCodewordsPerBlock:78}]},{ecCodewordsPerBlock:18,ecBlocks:[{numBlocks:4,dataCodewordsPerBlock:31}]},{ecCodewordsPerBlock:18,ecBlocks:[{numBlocks:2,dataCodewordsPerBlock:14},{numBlocks:4,dataCodewordsPerBlock:15}]},{ecCodewordsPerBlock:26,ecBlocks:[{numBlocks:4,dataCodewordsPerBlock:13},{numBlocks:1,dataCodewordsPerBlock:14}]}]},{infoBits:34236,versionNumber:8,alignmentPatternCenters:[6,24,42],errorCorrectionLevels:[{ecCodewordsPerBlock:24,ecBlocks:[{numBlocks:2,dataCodewordsPerBlock:97}]},{ecCodewordsPerBlock:22,ecBlocks:[{numBlocks:2,dataCodewordsPerBlock:38},{numBlocks:2,dataCodewordsPerBlock:39}]},{ecCodewordsPerBlock:22,ecBlocks:[{numBlocks:4,dataCodewordsPerBlock:18},{numBlocks:2,dataCodewordsPerBlock:19}]},{ecCodewordsPerBlock:26,ecBlocks:[{numBlocks:4,dataCodewordsPerBlock:14},{numBlocks:2,dataCodewordsPerBlock:15}]}]},{infoBits:39577,versionNumber:9,alignmentPatternCenters:[6,26,46],errorCorrectionLevels:[{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:2,dataCodewordsPerBlock:116}]},{ecCodewordsPerBlock:22,ecBlocks:[{numBlocks:3,dataCodewordsPerBlock:36},{numBlocks:2,dataCodewordsPerBlock:37}]},{ecCodewordsPerBlock:20,ecBlocks:[{numBlocks:4,dataCodewordsPerBlock:16},{numBlocks:4,dataCodewordsPerBlock:17}]},{ecCodewordsPerBlock:24,ecBlocks:[{numBlocks:4,dataCodewordsPerBlock:12},{numBlocks:4,dataCodewordsPerBlock:13}]}]},{infoBits:42195,versionNumber:10,alignmentPatternCenters:[6,28,50],errorCorrectionLevels:[{ecCodewordsPerBlock:18,ecBlocks:[{numBlocks:2,dataCodewordsPerBlock:68},{numBlocks:2,dataCodewordsPerBlock:69}]},{ecCodewordsPerBlock:26,ecBlocks:[{numBlocks:4,dataCodewordsPerBlock:43},{numBlocks:1,dataCodewordsPerBlock:44}]},{ecCodewordsPerBlock:24,ecBlocks:[{numBlocks:6,dataCodewordsPerBlock:19},{numBlocks:2,dataCodewordsPerBlock:20}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:6,dataCodewordsPerBlock:15},{numBlocks:2,dataCodewordsPerBlock:16}]}]},{infoBits:48118,versionNumber:11,alignmentPatternCenters:[6,30,54],errorCorrectionLevels:[{ecCodewordsPerBlock:20,ecBlocks:[{numBlocks:4,dataCodewordsPerBlock:81}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:1,dataCodewordsPerBlock:50},{numBlocks:4,dataCodewordsPerBlock:51}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:4,dataCodewordsPerBlock:22},{numBlocks:4,dataCodewordsPerBlock:23}]},{ecCodewordsPerBlock:24,ecBlocks:[{numBlocks:3,dataCodewordsPerBlock:12},{numBlocks:8,dataCodewordsPerBlock:13}]}]},{infoBits:51042,versionNumber:12,alignmentPatternCenters:[6,32,58],errorCorrectionLevels:[{ecCodewordsPerBlock:24,ecBlocks:[{numBlocks:2,dataCodewordsPerBlock:92},{numBlocks:2,dataCodewordsPerBlock:93}]},{ecCodewordsPerBlock:22,ecBlocks:[{numBlocks:6,dataCodewordsPerBlock:36},{numBlocks:2,dataCodewordsPerBlock:37}]},{ecCodewordsPerBlock:26,ecBlocks:[{numBlocks:4,dataCodewordsPerBlock:20},{numBlocks:6,dataCodewordsPerBlock:21}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:7,dataCodewordsPerBlock:14},{numBlocks:4,dataCodewordsPerBlock:15}]}]},{infoBits:55367,versionNumber:13,alignmentPatternCenters:[6,34,62],errorCorrectionLevels:[{ecCodewordsPerBlock:26,ecBlocks:[{numBlocks:4,dataCodewordsPerBlock:107}]},{ecCodewordsPerBlock:22,ecBlocks:[{numBlocks:8,dataCodewordsPerBlock:37},{numBlocks:1,dataCodewordsPerBlock:38}]},{ecCodewordsPerBlock:24,ecBlocks:[{numBlocks:8,dataCodewordsPerBlock:20},{numBlocks:4,dataCodewordsPerBlock:21}]},{ecCodewordsPerBlock:22,ecBlocks:[{numBlocks:12,dataCodewordsPerBlock:11},{numBlocks:4,dataCodewordsPerBlock:12}]}]},{infoBits:58893,versionNumber:14,alignmentPatternCenters:[6,26,46,66],errorCorrectionLevels:[{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:3,dataCodewordsPerBlock:115},{numBlocks:1,dataCodewordsPerBlock:116}]},{ecCodewordsPerBlock:24,ecBlocks:[{numBlocks:4,dataCodewordsPerBlock:40},{numBlocks:5,dataCodewordsPerBlock:41}]},{ecCodewordsPerBlock:20,ecBlocks:[{numBlocks:11,dataCodewordsPerBlock:16},{numBlocks:5,dataCodewordsPerBlock:17}]},{ecCodewordsPerBlock:24,ecBlocks:[{numBlocks:11,dataCodewordsPerBlock:12},{numBlocks:5,dataCodewordsPerBlock:13}]}]},{infoBits:63784,versionNumber:15,alignmentPatternCenters:[6,26,48,70],errorCorrectionLevels:[{ecCodewordsPerBlock:22,ecBlocks:[{numBlocks:5,dataCodewordsPerBlock:87},{numBlocks:1,dataCodewordsPerBlock:88}]},{ecCodewordsPerBlock:24,ecBlocks:[{numBlocks:5,dataCodewordsPerBlock:41},{numBlocks:5,dataCodewordsPerBlock:42}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:5,dataCodewordsPerBlock:24},{numBlocks:7,dataCodewordsPerBlock:25}]},{ecCodewordsPerBlock:24,ecBlocks:[{numBlocks:11,dataCodewordsPerBlock:12},{numBlocks:7,dataCodewordsPerBlock:13}]}]},{infoBits:68472,versionNumber:16,alignmentPatternCenters:[6,26,50,74],errorCorrectionLevels:[{ecCodewordsPerBlock:24,ecBlocks:[{numBlocks:5,dataCodewordsPerBlock:98},{numBlocks:1,dataCodewordsPerBlock:99}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:7,dataCodewordsPerBlock:45},{numBlocks:3,dataCodewordsPerBlock:46}]},{ecCodewordsPerBlock:24,ecBlocks:[{numBlocks:15,dataCodewordsPerBlock:19},{numBlocks:2,dataCodewordsPerBlock:20}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:3,dataCodewordsPerBlock:15},{numBlocks:13,dataCodewordsPerBlock:16}]}]},{infoBits:70749,versionNumber:17,alignmentPatternCenters:[6,30,54,78],errorCorrectionLevels:[{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:1,dataCodewordsPerBlock:107},{numBlocks:5,dataCodewordsPerBlock:108}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:10,dataCodewordsPerBlock:46},{numBlocks:1,dataCodewordsPerBlock:47}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:1,dataCodewordsPerBlock:22},{numBlocks:15,dataCodewordsPerBlock:23}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:2,dataCodewordsPerBlock:14},{numBlocks:17,dataCodewordsPerBlock:15}]}]},{infoBits:76311,versionNumber:18,alignmentPatternCenters:[6,30,56,82],errorCorrectionLevels:[{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:5,dataCodewordsPerBlock:120},{numBlocks:1,dataCodewordsPerBlock:121}]},{ecCodewordsPerBlock:26,ecBlocks:[{numBlocks:9,dataCodewordsPerBlock:43},{numBlocks:4,dataCodewordsPerBlock:44}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:17,dataCodewordsPerBlock:22},{numBlocks:1,dataCodewordsPerBlock:23}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:2,dataCodewordsPerBlock:14},{numBlocks:19,dataCodewordsPerBlock:15}]}]},{infoBits:79154,versionNumber:19,alignmentPatternCenters:[6,30,58,86],errorCorrectionLevels:[{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:3,dataCodewordsPerBlock:113},{numBlocks:4,dataCodewordsPerBlock:114}]},{ecCodewordsPerBlock:26,ecBlocks:[{numBlocks:3,dataCodewordsPerBlock:44},{numBlocks:11,dataCodewordsPerBlock:45}]},{ecCodewordsPerBlock:26,ecBlocks:[{numBlocks:17,dataCodewordsPerBlock:21},{numBlocks:4,dataCodewordsPerBlock:22}]},{ecCodewordsPerBlock:26,ecBlocks:[{numBlocks:9,dataCodewordsPerBlock:13},{numBlocks:16,dataCodewordsPerBlock:14}]}]},{infoBits:84390,versionNumber:20,alignmentPatternCenters:[6,34,62,90],errorCorrectionLevels:[{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:3,dataCodewordsPerBlock:107},{numBlocks:5,dataCodewordsPerBlock:108}]},{ecCodewordsPerBlock:26,ecBlocks:[{numBlocks:3,dataCodewordsPerBlock:41},{numBlocks:13,dataCodewordsPerBlock:42}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:15,dataCodewordsPerBlock:24},{numBlocks:5,dataCodewordsPerBlock:25}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:15,dataCodewordsPerBlock:15},{numBlocks:10,dataCodewordsPerBlock:16}]}]},{infoBits:87683,versionNumber:21,alignmentPatternCenters:[6,28,50,72,94],errorCorrectionLevels:[{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:4,dataCodewordsPerBlock:116},{numBlocks:4,dataCodewordsPerBlock:117}]},{ecCodewordsPerBlock:26,ecBlocks:[{numBlocks:17,dataCodewordsPerBlock:42}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:17,dataCodewordsPerBlock:22},{numBlocks:6,dataCodewordsPerBlock:23}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:19,dataCodewordsPerBlock:16},{numBlocks:6,dataCodewordsPerBlock:17}]}]},{infoBits:92361,versionNumber:22,alignmentPatternCenters:[6,26,50,74,98],errorCorrectionLevels:[{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:2,dataCodewordsPerBlock:111},{numBlocks:7,dataCodewordsPerBlock:112}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:17,dataCodewordsPerBlock:46}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:7,dataCodewordsPerBlock:24},{numBlocks:16,dataCodewordsPerBlock:25}]},{ecCodewordsPerBlock:24,ecBlocks:[{numBlocks:34,dataCodewordsPerBlock:13}]}]},{infoBits:96236,versionNumber:23,alignmentPatternCenters:[6,30,54,74,102],errorCorrectionLevels:[{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:4,dataCodewordsPerBlock:121},{numBlocks:5,dataCodewordsPerBlock:122}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:4,dataCodewordsPerBlock:47},{numBlocks:14,dataCodewordsPerBlock:48}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:11,dataCodewordsPerBlock:24},{numBlocks:14,dataCodewordsPerBlock:25}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:16,dataCodewordsPerBlock:15},{numBlocks:14,dataCodewordsPerBlock:16}]}]},{infoBits:102084,versionNumber:24,alignmentPatternCenters:[6,28,54,80,106],errorCorrectionLevels:[{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:6,dataCodewordsPerBlock:117},{numBlocks:4,dataCodewordsPerBlock:118}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:6,dataCodewordsPerBlock:45},{numBlocks:14,dataCodewordsPerBlock:46}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:11,dataCodewordsPerBlock:24},{numBlocks:16,dataCodewordsPerBlock:25}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:30,dataCodewordsPerBlock:16},{numBlocks:2,dataCodewordsPerBlock:17}]}]},{infoBits:102881,versionNumber:25,alignmentPatternCenters:[6,32,58,84,110],errorCorrectionLevels:[{ecCodewordsPerBlock:26,ecBlocks:[{numBlocks:8,dataCodewordsPerBlock:106},{numBlocks:4,dataCodewordsPerBlock:107}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:8,dataCodewordsPerBlock:47},{numBlocks:13,dataCodewordsPerBlock:48}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:7,dataCodewordsPerBlock:24},{numBlocks:22,dataCodewordsPerBlock:25}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:22,dataCodewordsPerBlock:15},{numBlocks:13,dataCodewordsPerBlock:16}]}]},{infoBits:110507,versionNumber:26,alignmentPatternCenters:[6,30,58,86,114],errorCorrectionLevels:[{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:10,dataCodewordsPerBlock:114},{numBlocks:2,dataCodewordsPerBlock:115}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:19,dataCodewordsPerBlock:46},{numBlocks:4,dataCodewordsPerBlock:47}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:28,dataCodewordsPerBlock:22},{numBlocks:6,dataCodewordsPerBlock:23}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:33,dataCodewordsPerBlock:16},{numBlocks:4,dataCodewordsPerBlock:17}]}]},{infoBits:110734,versionNumber:27,alignmentPatternCenters:[6,34,62,90,118],errorCorrectionLevels:[{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:8,dataCodewordsPerBlock:122},{numBlocks:4,dataCodewordsPerBlock:123}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:22,dataCodewordsPerBlock:45},{numBlocks:3,dataCodewordsPerBlock:46}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:8,dataCodewordsPerBlock:23},{numBlocks:26,dataCodewordsPerBlock:24}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:12,dataCodewordsPerBlock:15},{numBlocks:28,dataCodewordsPerBlock:16}]}]},{infoBits:117786,versionNumber:28,alignmentPatternCenters:[6,26,50,74,98,122],errorCorrectionLevels:[{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:3,dataCodewordsPerBlock:117},{numBlocks:10,dataCodewordsPerBlock:118}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:3,dataCodewordsPerBlock:45},{numBlocks:23,dataCodewordsPerBlock:46}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:4,dataCodewordsPerBlock:24},{numBlocks:31,dataCodewordsPerBlock:25}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:11,dataCodewordsPerBlock:15},{numBlocks:31,dataCodewordsPerBlock:16}]}]},{infoBits:119615,versionNumber:29,alignmentPatternCenters:[6,30,54,78,102,126],errorCorrectionLevels:[{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:7,dataCodewordsPerBlock:116},{numBlocks:7,dataCodewordsPerBlock:117}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:21,dataCodewordsPerBlock:45},{numBlocks:7,dataCodewordsPerBlock:46}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:1,dataCodewordsPerBlock:23},{numBlocks:37,dataCodewordsPerBlock:24}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:19,dataCodewordsPerBlock:15},{numBlocks:26,dataCodewordsPerBlock:16}]}]},{infoBits:126325,versionNumber:30,alignmentPatternCenters:[6,26,52,78,104,130],errorCorrectionLevels:[{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:5,dataCodewordsPerBlock:115},{numBlocks:10,dataCodewordsPerBlock:116}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:19,dataCodewordsPerBlock:47},{numBlocks:10,dataCodewordsPerBlock:48}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:15,dataCodewordsPerBlock:24},{numBlocks:25,dataCodewordsPerBlock:25}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:23,dataCodewordsPerBlock:15},{numBlocks:25,dataCodewordsPerBlock:16}]}]},{infoBits:127568,versionNumber:31,alignmentPatternCenters:[6,30,56,82,108,134],errorCorrectionLevels:[{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:13,dataCodewordsPerBlock:115},{numBlocks:3,dataCodewordsPerBlock:116}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:2,dataCodewordsPerBlock:46},{numBlocks:29,dataCodewordsPerBlock:47}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:42,dataCodewordsPerBlock:24},{numBlocks:1,dataCodewordsPerBlock:25}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:23,dataCodewordsPerBlock:15},{numBlocks:28,dataCodewordsPerBlock:16}]}]},{infoBits:133589,versionNumber:32,alignmentPatternCenters:[6,34,60,86,112,138],errorCorrectionLevels:[{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:17,dataCodewordsPerBlock:115}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:10,dataCodewordsPerBlock:46},{numBlocks:23,dataCodewordsPerBlock:47}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:10,dataCodewordsPerBlock:24},{numBlocks:35,dataCodewordsPerBlock:25}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:19,dataCodewordsPerBlock:15},{numBlocks:35,dataCodewordsPerBlock:16}]}]},{infoBits:136944,versionNumber:33,alignmentPatternCenters:[6,30,58,86,114,142],errorCorrectionLevels:[{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:17,dataCodewordsPerBlock:115},{numBlocks:1,dataCodewordsPerBlock:116}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:14,dataCodewordsPerBlock:46},{numBlocks:21,dataCodewordsPerBlock:47}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:29,dataCodewordsPerBlock:24},{numBlocks:19,dataCodewordsPerBlock:25}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:11,dataCodewordsPerBlock:15},{numBlocks:46,dataCodewordsPerBlock:16}]}]},{infoBits:141498,versionNumber:34,alignmentPatternCenters:[6,34,62,90,118,146],errorCorrectionLevels:[{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:13,dataCodewordsPerBlock:115},{numBlocks:6,dataCodewordsPerBlock:116}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:14,dataCodewordsPerBlock:46},{numBlocks:23,dataCodewordsPerBlock:47}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:44,dataCodewordsPerBlock:24},{numBlocks:7,dataCodewordsPerBlock:25}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:59,dataCodewordsPerBlock:16},{numBlocks:1,dataCodewordsPerBlock:17}]}]},{infoBits:145311,versionNumber:35,alignmentPatternCenters:[6,30,54,78,102,126,150],errorCorrectionLevels:[{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:12,dataCodewordsPerBlock:121},{numBlocks:7,dataCodewordsPerBlock:122}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:12,dataCodewordsPerBlock:47},{numBlocks:26,dataCodewordsPerBlock:48}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:39,dataCodewordsPerBlock:24},{numBlocks:14,dataCodewordsPerBlock:25}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:22,dataCodewordsPerBlock:15},{numBlocks:41,dataCodewordsPerBlock:16}]}]},{infoBits:150283,versionNumber:36,alignmentPatternCenters:[6,24,50,76,102,128,154],errorCorrectionLevels:[{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:6,dataCodewordsPerBlock:121},{numBlocks:14,dataCodewordsPerBlock:122}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:6,dataCodewordsPerBlock:47},{numBlocks:34,dataCodewordsPerBlock:48}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:46,dataCodewordsPerBlock:24},{numBlocks:10,dataCodewordsPerBlock:25}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:2,dataCodewordsPerBlock:15},{numBlocks:64,dataCodewordsPerBlock:16}]}]},{infoBits:152622,versionNumber:37,alignmentPatternCenters:[6,28,54,80,106,132,158],errorCorrectionLevels:[{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:17,dataCodewordsPerBlock:122},{numBlocks:4,dataCodewordsPerBlock:123}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:29,dataCodewordsPerBlock:46},{numBlocks:14,dataCodewordsPerBlock:47}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:49,dataCodewordsPerBlock:24},{numBlocks:10,dataCodewordsPerBlock:25}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:24,dataCodewordsPerBlock:15},{numBlocks:46,dataCodewordsPerBlock:16}]}]},{infoBits:158308,versionNumber:38,alignmentPatternCenters:[6,32,58,84,110,136,162],errorCorrectionLevels:[{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:4,dataCodewordsPerBlock:122},{numBlocks:18,dataCodewordsPerBlock:123}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:13,dataCodewordsPerBlock:46},{numBlocks:32,dataCodewordsPerBlock:47}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:48,dataCodewordsPerBlock:24},{numBlocks:14,dataCodewordsPerBlock:25}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:42,dataCodewordsPerBlock:15},{numBlocks:32,dataCodewordsPerBlock:16}]}]},{infoBits:161089,versionNumber:39,alignmentPatternCenters:[6,26,54,82,110,138,166],errorCorrectionLevels:[{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:20,dataCodewordsPerBlock:117},{numBlocks:4,dataCodewordsPerBlock:118}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:40,dataCodewordsPerBlock:47},{numBlocks:7,dataCodewordsPerBlock:48}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:43,dataCodewordsPerBlock:24},{numBlocks:22,dataCodewordsPerBlock:25}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:10,dataCodewordsPerBlock:15},{numBlocks:67,dataCodewordsPerBlock:16}]}]},{infoBits:167017,versionNumber:40,alignmentPatternCenters:[6,30,58,86,114,142,170],errorCorrectionLevels:[{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:19,dataCodewordsPerBlock:118},{numBlocks:6,dataCodewordsPerBlock:119}]},{ecCodewordsPerBlock:28,ecBlocks:[{numBlocks:18,dataCodewordsPerBlock:47},{numBlocks:31,dataCodewordsPerBlock:48}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:34,dataCodewordsPerBlock:24},{numBlocks:34,dataCodewordsPerBlock:25}]},{ecCodewordsPerBlock:30,ecBlocks:[{numBlocks:20,dataCodewordsPerBlock:15},{numBlocks:61,dataCodewordsPerBlock:16}]}]}]},function(o,e,r){"use strict";Object.defineProperty(e,"__esModule",{value:!0});var t=r(0);function c(o,e,r,t){var c=o.x-e.x+r.x-t.x,s=o.y-e.y+r.y-t.y;if(0===c&&0===s)return{a11:e.x-o.x,a12:e.y-o.y,a13:0,a21:r.x-e.x,a22:r.y-e.y,a23:0,a31:o.x,a32:o.y,a33:1};var a=e.x-r.x,n=t.x-r.x,d=e.y-r.y,l=t.y-r.y,i=a*l-n*d,B=(c*l-n*s)/i,k=(a*s-c*d)/i;return{a11:e.x-o.x+B*e.x,a12:e.y-o.y+B*e.y,a13:B,a21:t.x-o.x+k*t.x,a22:t.y-o.y+k*t.y,a23:k,a31:o.x,a32:o.y,a33:1}}e.extract=function(o,e){for(var r,s,a=function(o,e,r,t){var s=c(o,e,r,t);return{a11:s.a22*s.a33-s.a23*s.a32,a12:s.a13*s.a32-s.a12*s.a33,a13:s.a12*s.a23-s.a13*s.a22,a21:s.a23*s.a31-s.a21*s.a33,a22:s.a11*s.a33-s.a13*s.a31,a23:s.a13*s.a21-s.a11*s.a23,a31:s.a21*s.a32-s.a22*s.a31,a32:s.a12*s.a31-s.a11*s.a32,a33:s.a11*s.a22-s.a12*s.a21}}({x:3.5,y:3.5},{x:e.dimension-3.5,y:3.5},{x:e.dimension-6.5,y:e.dimension-6.5},{x:3.5,y:e.dimension-3.5}),n=c(e.topLeft,e.topRight,e.alignmentPattern,e.bottomLeft),d=(s=a,{a11:(r=n).a11*s.a11+r.a21*s.a12+r.a31*s.a13,a12:r.a12*s.a11+r.a22*s.a12+r.a32*s.a13,a13:r.a13*s.a11+r.a23*s.a12+r.a33*s.a13,a21:r.a11*s.a21+r.a21*s.a22+r.a31*s.a23,a22:r.a12*s.a21+r.a22*s.a22+r.a32*s.a23,a23:r.a13*s.a21+r.a23*s.a22+r.a33*s.a23,a31:r.a11*s.a31+r.a21*s.a32+r.a31*s.a33,a32:r.a12*s.a31+r.a22*s.a32+r.a32*s.a33,a33:r.a13*s.a31+r.a23*s.a32+r.a33*s.a33}),l=t.BitMatrix.createEmpty(e.dimension,e.dimension),i=function(o,e){var r=d.a13*o+d.a23*e+d.a33;return{x:(d.a11*o+d.a21*e+d.a31)/r,y:(d.a12*o+d.a22*e+d.a32)/r}},B=0;B<e.dimension;B++)for(var k=0;k<e.dimension;k++){var u=i(k+.5,B+.5);l.set(k,B,o.get(Math.floor(u.x),Math.floor(u.y)))}return{matrix:l,mappingFunction:i}}},function(o,e,r){"use strict";Object.defineProperty(e,"__esModule",{value:!0});var t=function(o,e){return Math.sqrt(Math.pow(e.x-o.x,2)+Math.pow(e.y-o.y,2))};function c(o){return o.reduce((function(o,e){return o+e}))}function s(o,e,r,c){var s,a,n,d,l=[{x:Math.floor(o.x),y:Math.floor(o.y)}],i=Math.abs(e.y-o.y)>Math.abs(e.x-o.x);i?(s=Math.floor(o.y),a=Math.floor(o.x),n=Math.floor(e.y),d=Math.floor(e.x)):(s=Math.floor(o.x),a=Math.floor(o.y),n=Math.floor(e.x),d=Math.floor(e.y));for(var B=Math.abs(n-s),k=Math.abs(d-a),u=Math.floor(-B/2),C=s<n?1:-1,m=a<d?1:-1,f=!0,w=s,P=a;w!==n+C;w+=C){var v=i?P:w,h=i?w:P;if(r.get(v,h)!==f&&(f=!f,l.push({x:v,y:h}),l.length===c+1))break;if((u+=k)>0){if(P===d)break;P+=m,u-=B}}for(var y=[],p=0;p<c;p++)l[p]&&l[p+1]?y.push(t(l[p],l[p+1])):y.push(0);return y}function a(o,e,r,t){var c,a=e.y-o.y,n=e.x-o.x,d=s(o,e,r,Math.ceil(t/2)),l=s(o,{x:o.x-n,y:o.y-a},r,Math.ceil(t/2)),i=d.shift()+l.shift()-1;return(c=l.concat(i)).concat.apply(c,d)}function n(o,e){var r=c(o)/c(e),t=0;return e.forEach((function(e,c){t+=Math.pow(o[c]-e*r,2)})),{averageSize:r,error:t}}function d(o,e,r){try{var t=a(o,{x:-1,y:o.y},r,e.length),c=a(o,{x:o.x,y:-1},r,e.length),s=a(o,{x:Math.max(0,o.x-o.y)-1,y:Math.max(0,o.y-o.x)-1},r,e.length),d=a(o,{x:Math.min(r.width,o.x+o.y)+1,y:Math.min(r.height,o.y+o.x)+1},r,e.length),l=n(t,e),i=n(c,e),B=n(s,e),k=n(d,e),u=Math.sqrt(l.error*l.error+i.error*i.error+B.error*B.error+k.error*k.error),C=(l.averageSize+i.averageSize+B.averageSize+k.averageSize)/4;return u+(Math.pow(l.averageSize-C,2)+Math.pow(i.averageSize-C,2)+Math.pow(B.averageSize-C,2)+Math.pow(k.averageSize-C,2))/C}catch(o){return 1/0}}function l(o,e){for(var r=Math.round(e.x);o.get(r,Math.round(e.y));)r--;for(var t=Math.round(e.x);o.get(t,Math.round(e.y));)t++;for(var c=(r+t)/2,s=Math.round(e.y);o.get(Math.round(c),s);)s--;for(var a=Math.round(e.y);o.get(Math.round(c),a);)a++;return{x:c,y:(s+a)/2}}function i(o,e,r,s,n){var l,i,B;try{l=function(o,e,r,s){var n=(c(a(o,r,s,5))/7+c(a(o,e,s,5))/7+c(a(r,o,s,5))/7+c(a(e,o,s,5))/7)/4;if(n<1)throw new Error("Invalid module size");var d=Math.round(t(o,e)/n),l=Math.round(t(o,r)/n),i=Math.floor((d+l)/2)+7;switch(i%4){case 0:i++;break;case 2:i--}return{dimension:i,moduleSize:n}}(s,r,n,o),i=l.dimension,B=l.moduleSize}catch(o){return null}var k=r.x-s.x+n.x,u=r.y-s.y+n.y,C=(t(s,n)+t(s,r))/2/B,m=1-3/C,f={x:s.x+m*(k-s.x),y:s.y+m*(u-s.y)},w=e.map((function(e){var r=(e.top.startX+e.top.endX+e.bottom.startX+e.bottom.endX)/4,s=(e.top.y+e.bottom.y+1)/2;if(o.get(Math.floor(r),Math.floor(s))){var a=[e.top.endX-e.top.startX,e.bottom.endX-e.bottom.startX,e.bottom.y-e.top.y+1];c(a);return{x:r,y:s,score:d({x:Math.floor(r),y:Math.floor(s)},[1,1,1],o)+t({x:r,y:s},f)}}})).filter((function(o){return!!o})).sort((function(o,e){return o.score-e.score}));return{alignmentPattern:C>=15&&w.length?w[0]:f,dimension:i}}e.locate=function(o){for(var e=[],r=[],s=[],a=[],n=function(t){for(var n=0,d=!1,l=[0,0,0,0,0],i=function(e){var s=o.get(e,t);if(s===d)n++;else{l=[l[1],l[2],l[3],l[4],n],n=1,d=s;var i=c(l)/7,B=Math.abs(l[0]-i)<i&&Math.abs(l[1]-i)<i&&Math.abs(l[2]-3*i)<3*i&&Math.abs(l[3]-i)<i&&Math.abs(l[4]-i)<i&&!s,k=c(l.slice(-3))/3,u=Math.abs(l[2]-k)<k&&Math.abs(l[3]-k)<k&&Math.abs(l[4]-k)<k&&s;if(B){var C=e-l[3]-l[4],m=C-l[2],f={startX:m,endX:C,y:t};(w=r.filter((function(o){return m>=o.bottom.startX&&m<=o.bottom.endX||C>=o.bottom.startX&&m<=o.bottom.endX||m<=o.bottom.startX&&C>=o.bottom.endX&&l[2]/(o.bottom.endX-o.bottom.startX)<1.5&&l[2]/(o.bottom.endX-o.bottom.startX)>.5}))).length>0?w[0].bottom=f:r.push({top:f,bottom:f})}if(u){var w,P=e-l[4],v=P-l[3];f={startX:v,y:t,endX:P};(w=a.filter((function(o){return v>=o.bottom.startX&&v<=o.bottom.endX||P>=o.bottom.startX&&v<=o.bottom.endX||v<=o.bottom.startX&&P>=o.bottom.endX&&l[2]/(o.bottom.endX-o.bottom.startX)<1.5&&l[2]/(o.bottom.endX-o.bottom.startX)>.5}))).length>0?w[0].bottom=f:a.push({top:f,bottom:f})}}},B=-1;B<=o.width;B++)i(B);e.push.apply(e,r.filter((function(o){return o.bottom.y!==t&&o.bottom.y-o.top.y>=2}))),r=r.filter((function(o){return o.bottom.y===t})),s.push.apply(s,a.filter((function(o){return o.bottom.y!==t}))),a=a.filter((function(o){return o.bottom.y===t}))},B=0;B<=o.height;B++)n(B);e.push.apply(e,r.filter((function(o){return o.bottom.y-o.top.y>=2}))),s.push.apply(s,a);var k=e.filter((function(o){return o.bottom.y-o.top.y>=2})).map((function(e){var r=(e.top.startX+e.top.endX+e.bottom.startX+e.bottom.endX)/4,t=(e.top.y+e.bottom.y+1)/2;if(o.get(Math.round(r),Math.round(t))){var s=[e.top.endX-e.top.startX,e.bottom.endX-e.bottom.startX,e.bottom.y-e.top.y+1],a=c(s)/s.length;return{score:d({x:Math.round(r),y:Math.round(t)},[1,1,3,1,1],o),x:r,y:t,size:a}}})).filter((function(o){return!!o})).sort((function(o,e){return o.score-e.score})).map((function(o,e,r){if(e>4)return null;var t=r.filter((function(o,r){return e!==r})).map((function(e){return{x:e.x,y:e.y,score:e.score+Math.pow(e.size-o.size,2)/o.size,size:e.size}})).sort((function(o,e){return o.score-e.score}));if(t.length<2)return null;var c=o.score+t[0].score+t[1].score;return{points:[o].concat(t.slice(0,2)),score:c}})).filter((function(o){return!!o})).sort((function(o,e){return o.score-e.score}));if(0===k.length)return null;var u=function(o,e,r){var c,s,a,n,d,l,i,B=t(o,e),k=t(e,r),u=t(o,r);return k>=B&&k>=u?(d=(c=[e,o,r])[0],l=c[1],i=c[2]):u>=k&&u>=B?(d=(s=[o,e,r])[0],l=s[1],i=s[2]):(d=(a=[o,r,e])[0],l=a[1],i=a[2]),(i.x-l.x)*(d.y-l.y)-(i.y-l.y)*(d.x-l.x)<0&&(d=(n=[i,d])[0],i=n[1]),{bottomLeft:d,topLeft:l,topRight:i}}(k[0].points[0],k[0].points[1],k[0].points[2]),C=u.topRight,m=u.topLeft,f=u.bottomLeft,w=i(o,s,C,m,f),P=[];w&&P.push({alignmentPattern:{x:w.alignmentPattern.x,y:w.alignmentPattern.y},bottomLeft:{x:f.x,y:f.y},dimension:w.dimension,topLeft:{x:m.x,y:m.y},topRight:{x:C.x,y:C.y}});var v=l(o,C),h=l(o,m),y=l(o,f),p=i(o,s,v,h,y);return p&&P.push({alignmentPattern:{x:p.alignmentPattern.x,y:p.alignmentPattern.y},bottomLeft:{x:y.x,y:y.y},topLeft:{x:h.x,y:h.y},topRight:{x:v.x,y:v.y},dimension:p.dimension}),0===P.length?null:P}}]).default}));
//# sourceMappingURL=/sm/261261d91f249d4079ae119cfa50f739467d90fc365078a671172e0f499e862a.map
// 小橘3号 · 新版控制台前端逻辑（纯轮询，无 WebSocket）
(function() {
    console.log('小橘3号控制台逻辑已启动');

    // ==================== 0. 主题 / 音效开关（localStorage 记忆） ====================
    // 皮肤系统基础（界面文档 §10.1）：data-theme="orange" 橘色主题，默认深蓝不变。
    const THEME_KEY = 'xiaoju3_theme';

    function applyTheme(theme) {
        if (theme === 'orange') {
            document.documentElement.setAttribute('data-theme', 'orange');
        } else {
            document.documentElement.removeAttribute('data-theme');  // 默认深蓝主题
        }
    }
    applyTheme(getStoredTheme());

    function getStoredTheme() {
        try { return localStorage.getItem(THEME_KEY); } catch (e) { return null; }
    }

    // 主题切换函数（头部 🦊 按钮已删——#264 B2b 微调拍板：与桌宠菜单
    // 「切换主题」+设置页「界面偏好」双入口冗余）；toggleTheme 保留供
    // 桌宠菜单桥与设置页主题选择器共用
    function toggleTheme() {
        const next = getStoredTheme() === 'orange' ? '' : 'orange';
        try {
            if (next) localStorage.setItem(THEME_KEY, next);
            else localStorage.removeItem(THEME_KEY);
        } catch (e) { /* localStorage 不可用时仅本次会话生效 */ }
        applyTheme(next);
        showToast(next === 'orange' ? '已切换到橘色主题 🦊' : '已切换到深蓝主题');
    }

    // 矢量图标表（2026-10-29 队长要求去 Emoji 凑数）：状态按钮经 innerHTML
    // 换图标（textContent 会抹掉 SVG 露白）；路径=Lucide/Feather 线性风，
    // 与 index.html 顶栏静态图标同源同款，stroke=currentColor 随色态联动。
    const ICON_SVGS = (function (a) {
        return {
            bell: a + '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>',
            bellOff: a + '<path d="M13.73 21a2 2 0 0 1-3.46 0"/><path d="M18.63 13A17.89 17.89 0 0 1 18 8"/><path d="M6.26 6.26A5.86 5.86 0 0 0 6 8c0 7-3 9-3 9h14"/><path d="M18 8a6 6 0 0 0-9.33-5"/><line x1="1" y1="1" x2="23" y2="23"/></svg>',
            volume2: a + '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/></svg>',
            volumeX: a + '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg>',
            settings: a + '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
            library: a + '<path d="m16 6 4 14"/><path d="M12 6v14"/><path d="M8 8v12"/><path d="M4 4v16"/></svg>',
            message: a + '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
            trash: a + '<polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>',
            x: a + '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
            fileText: a + '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>',
            puzzle: a + '<path d="M19.439 7.85c-.049.322.059.648.289.878l1.568 1.568c.47.47.706 1.087.706 1.704s-.235 1.233-.706 1.704l-1.611 1.611a.98.98 0 0 1-.837.276c-.47-.07-.802-.48-.968-.925a2.501 2.501 0 1 0-3.214 3.214c.446.166.855.497.925.968a.979.979 0 0 1-.276.837l-1.61 1.61a2.404 2.404 0 0 1-1.705.707 2.402 2.402 0 0 1-1.704-.706l-1.568-1.568a1.026 1.026 0 0 0-.877-.29c-.493.074-.84.504-1.02.968a2.5 2.5 0 1 1-3.237-3.237c.464-.18.894-.527.967-1.02a1.026 1.026 0 0 0-.289-.877l-1.568-1.568A2.402 2.402 0 0 1 1.998 12c0-.617.236-1.234.706-1.704L4.23 8.77c.24-.24.581-.353.917-.303.515.077.877.528 1.073 1.01a2.5 2.5 0 1 0 3.259-3.259c-.482-.196-.933-.558-1.01-1.073-.05-.336.062-.676.303-.917l1.525-1.525A2.402 2.402 0 0 1 12 1.998c.617 0 1.234.236 1.704.706l1.568 1.568c.23.23.556.338.877.29.493-.074.84-.504 1.02-.968a2.5 2.5 0 1 1 3.237 3.237c-.464.18-.894.527-.967 1.02Z"/></svg>',
            zap: a + '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
            video: a + '<polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>',
            clock: a + '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
            droplet: a + '<path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"/></svg>',
            wind: a + '<path d="M9.59 4.59A2 2 0 1 1 11 8H2m10.59 11.41A2 2 0 1 0 14 16H2m15.73-8.27A2.5 2.5 0 1 1 19.5 12H2"/></svg>',
            chart: a + '<line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>',
            house: a + '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>',
            plug: a + '<path d="M12 22v-5"/><path d="M9 8V2"/><path d="M15 8V2"/><path d="M18 8v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8z"/></svg>',
            refresh: a + '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M3 21v-5h5"/></svg>'
        };
    })('<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">');

    // ==================== 现代确认弹窗（2026-10-29 队长指令：原生 confirm 全量退役） ====================
    // 对齐 DeepSeek 规范：深色半透明遮罩+居中白圆角卡+加粗标题+灰描述+核心
    // 点缀蓝胶囊主钮+右上 ×。z-index 50000，遮罩全屏覆盖=弹出期背景不可点。
    // Esc/遮罩空白点击/× 均为取消；Enter=确认。textContent 注入零 XSS 面。
    // showConfirm(title, message, onConfirm, opts)：
    //   opts.confirmText（默认'确定'）/ opts.cancelText（默认'取消'）/
    //   opts.showCancel（默认 true；false=单钮提示态）
    function showConfirm(title, message, onConfirm, opts) {
        opts = opts || {};
        const overlay = document.createElement('div');
        overlay.className = 'xj3-modal-overlay';
        const card = document.createElement('div');
        card.className = 'xj3-modal-card';
        card.setAttribute('role', 'dialog');
        card.setAttribute('aria-modal', 'true');
        const closeBtn = document.createElement('button');
        closeBtn.className = 'xj3-modal-close';
        closeBtn.setAttribute('aria-label', '关闭');
        closeBtn.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
        const titleEl = document.createElement('div');
        titleEl.className = 'xj3-modal-title';
        titleEl.textContent = title;
        const msgEl = document.createElement('p');
        msgEl.className = 'xj3-modal-msg';
        msgEl.textContent = message;
        const btns = document.createElement('div');
        btns.className = 'xj3-modal-btns';
        let settled = false;
        function close(result) {
            if (settled) return;
            settled = true;
            document.removeEventListener('keydown', onKey, true);
            overlay.remove();
            if (result === 'confirm' && typeof onConfirm === 'function') onConfirm();
        }
        function onKey(e) {
            if (e.key === 'Escape') close('cancel');
            else if (e.key === 'Enter') { e.preventDefault(); close('confirm'); }
        }
        if (opts.showCancel !== false) {
            const cancelBtn = document.createElement('button');
            cancelBtn.className = 'xj3-modal-btn xj3-modal-btn-secondary';
            cancelBtn.textContent = opts.cancelText || '取消';
            cancelBtn.addEventListener('click', function () { close('cancel'); });
            btns.appendChild(cancelBtn);
        }
        const okBtn = document.createElement('button');
        okBtn.className = 'xj3-modal-btn xj3-modal-btn-primary';
        okBtn.textContent = opts.confirmText || '确定';
        okBtn.addEventListener('click', function () { close('confirm'); });
        btns.appendChild(okBtn);
        closeBtn.addEventListener('click', function () { close('cancel'); });
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) close('cancel');
        });
        document.addEventListener('keydown', onKey, true);
        card.appendChild(closeBtn);
        card.appendChild(titleEl);
        card.appendChild(msgEl);
        card.appendChild(btns);
        overlay.appendChild(card);
        document.body.appendChild(overlay);
        okBtn.focus();
    }
    window.showConfirm = showConfirm;   // 全局可达（控制台调试/外部脚本）

    // ==================== 手机端 API_BASE（APK 遥控壳，2026-10-29） ====================
    // 桌面端零变化：__XJ3_API_BASE=''=同源相对路径。APK 内经 localStorage
    // 'xj3_api_base' 配置（如 http://192.168.x.x:5003），fetch/EventSource
    // 统一前缀；Capacitor 环境探活失败/未配置 → 弹后端地址配置卡。
    window.__XJ3_API_BASE = '';
    (function () {
        try {
            if (window.Capacitor) {
                window.__XJ3_API_BASE =
                    localStorage.getItem('xj3_api_base') || '';
            }
        } catch (e) { /* localStorage 不可用：按同源处理 */ }
        const origFetch = window.fetch ? window.fetch.bind(window) : null;
        if (origFetch) {
            window.fetch = function (input, init) {
                try {
                    if (typeof input === 'string' && input.charAt(0) === '/'
                            && window.__XJ3_API_BASE) {
                        input = window.__XJ3_API_BASE + input;
                    }
                } catch (e) { /* 前缀失败按原请求发出 */ }
                return origFetch(input, init);
            };
        }
        const OrigES = window.EventSource;
        if (OrigES) {
            window.EventSource = function (url, cfg) {
                if (typeof url === 'string' && url.charAt(0) === '/'
                        && window.__XJ3_API_BASE) {
                    url = window.__XJ3_API_BASE + url;
                }
                return new OrigES(url, cfg);
            };
            window.EventSource.prototype = OrigES.prototype;
        }
    })();
    function parsePairingPayload(text) {
        // 解析二维码载荷：xiaoju3://connect?ips=a,b&port=5003（新）/
        // http://ip:port 直填（兼容手输）。返回候选 base 列表。
        const s = String(text || '').trim();
        if (!s) return [];
        const m = s.match(/^xiaoju3:\/\/connect\?([^#]+)/);
        if (m) {
            const q = new URLSearchParams(m[1]);
            const ips = (q.get('ips') || '').split(',')
                .map(function (x) { return x.trim(); }).filter(Boolean);
            const port = q.get('port') || '5003';
            return ips.map(function (ip) {
                return 'http://' + ip + ':' + port;
            });
        }
        if (/^http:\/\//.test(s)) return [s.replace(/\/+$/, '')];
        return [];
    }
    function pairConnect(candidates) {
        // 逐候选探活，首个 /api/health ok 的写入 localStorage 并重载
        let i = 0;
        function next() {
            if (i >= candidates.length) {
                showToast('❌ 扫码的地址都连不上，主人检查一下网络～');
                return;
            }
            const base = candidates[i++];
            fetch(base + '/api/health').then(function (r) { return r.json(); })
                .then(function (j) {
                    if (!j || j.status !== 'ok') throw new Error('not ok');
                    try { localStorage.setItem('xj3_api_base', base); }
                    catch (e) {}
                    window.__XJ3_API_BASE = base;
                    window.location.reload();
                })
                .catch(next);
        }
        next();
    }
    // ── 扫码器：getUserMedia 后摄 + BarcodeDetector 加速（安卓 WebView
    // 渐进可用）+ jsQR 逐帧兜底；取消键收场 ──
    function openPairScanner() {
        const overlay = document.createElement('div');
        overlay.className = 'xj3-modal-overlay';
        overlay.style.zIndex = '60000';
        const card = document.createElement('div');
        card.className = 'xj3-modal-card';
        card.style.cssText += 'padding:16px;';
        const titleEl = document.createElement('div');
        titleEl.className = 'xj3-modal-title';
        titleEl.textContent = '对准电脑上的二维码';
        const video = document.createElement('video');
        video.setAttribute('playsinline', '');
        video.muted = true;
        video.style.cssText = 'width:100%;border-radius:10px;background:#111827;';
        const hint = document.createElement('div');
        hint.style.cssText = 'font-size:12px;color:#6b7280;margin-top:8px;';
        hint.textContent = '打开后请稍候——首次会请求相机权限';
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'xj3-modal-btn xj3-modal-btn-secondary';
        cancelBtn.style.cssText += 'margin-top:12px;';
        cancelBtn.textContent = '取消';
        card.appendChild(titleEl);
        card.appendChild(video);
        card.appendChild(hint);
        card.appendChild(cancelBtn);
        overlay.appendChild(card);
        document.body.appendChild(overlay);
        let stopped = false;
        let streamRef = null;
        function stop() {
            stopped = true;
            if (streamRef) streamRef.getTracks().forEach(function (t) { t.stop(); });
            overlay.remove();
        }
        cancelBtn.addEventListener('click', function () { stop(); });
        function onDecode(text) {
            if (stopped) return;
            stop();
            const candidates = parsePairingPayload(text);
            if (candidates.length) {
                hint.textContent = '已识别，正在连接…';
                pairConnect(candidates);
            } else {
                showToast('二维码不是小橘的配对码');
            }
        }
        async function run() {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                hint.textContent = '此环境不支持相机，请用下方手动输入';
                return;
            }
            try {
                streamRef = await navigator.mediaDevices.getUserMedia(
                    { video: { facingMode: 'environment' }, audio: false });
            } catch (e) {
                hint.textContent = '相机打开失败（权限未授予）——可用下方手动输入';
                return;
            }
            video.srcObject = streamRef;
            await video.play();
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d', { willReadFrequently: true });
            const Detector = window.BarcodeDetector || null;
            let detector = null;
            if (Detector) {
                try { detector = new Detector({ formats: ['qr_code'] }); }
                catch (e) { detector = null; }
            }
            (function loop() {
                if (stopped) return;
                if (video.readyState >= 2) {
                    canvas.width = video.videoWidth;
                    canvas.height = video.videoHeight;
                    if (canvas.width && canvas.height) {
                        ctx.drawImage(video, 0, 0);
                        const tick = function (text) {
                            if (text) { onDecode(text); return; }
                            setTimeout(loop, 180);
                        };
                        if (detector) {
                            detector.detect(video).then(function (bars) {
                                tick(bars && bars.length ? bars[0].rawValue : null);
                            }).catch(function () { tick(null); });
                            return;
                        }
                        try {
                            const img = ctx.getImageData(0, 0, canvas.width,
                                                        canvas.height);
                            const found = jsQR(img.data, img.width, img.height);
                            tick(found ? found.data : null);
                            return;
                        } catch (e) { /* 帧未就绪，下一轮 */ }
                    }
                }
                setTimeout(loop, 180);
            })();
        }
        run();
    }
    function showPairGate() {
        // 首启配对门：扫码为主（像正经 App），手动输入折叠兜底
        const overlay = document.createElement('div');
        overlay.className = 'xj3-modal-overlay';
        overlay.style.zIndex = '60000';
        const card = document.createElement('div');
        card.className = 'xj3-modal-card';
        card.setAttribute('role', 'dialog');
        card.setAttribute('aria-modal', 'true');
        const titleEl = document.createElement('div');
        titleEl.className = 'xj3-modal-title';
        titleEl.textContent = '连接小橘';
        const msgEl = document.createElement('p');
        msgEl.className = 'xj3-modal-msg';
        msgEl.textContent = '用摄像头扫电脑「连接手机」卡片上的二维码，一步连上你的小橘。';
        const scanBtn = document.createElement('button');
        scanBtn.className = 'xj3-modal-btn xj3-modal-btn-primary';
        scanBtn.style.cssText += 'height:46px;font-size:15px;width:100%;';
        scanBtn.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-3px;margin-right:6px"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>扫码连接';
        scanBtn.addEventListener('click', function () {
            overlay.remove();
            openPairScanner();
        });
        const manual = document.createElement('details');
        manual.style.cssText = 'margin-top:14px;font-size:12px;color:#6b7280;';
        const summary = document.createElement('summary');
        summary.textContent = '手动输入地址（备用）';
        summary.style.cssText = 'cursor:pointer;';
        const input = document.createElement('input');
        input.type = 'text';
        input.placeholder = 'http://192.168.31.50:5003';
        input.style.cssText = 'width:100%;box-sizing:border-box;margin-top:8px;'
            + 'padding:10px 14px;border:1px solid #d1d5db;border-radius:10px;'
            + 'font-size:14px;color:#1f2937;';
        const saveBtn = document.createElement('button');
        saveBtn.className = 'xj3-modal-btn xj3-modal-btn-secondary';
        saveBtn.style.cssText += 'margin-top:8px;height:34px;';
        saveBtn.textContent = '保存并连接';
        saveBtn.addEventListener('click', function () {
            const base = input.value.trim().replace(/\/+$/, '');
            if (!base) return;
            try { localStorage.setItem('xj3_api_base', base); } catch (e) {}
            window.__XJ3_API_BASE = base;
            overlay.remove();
            window.location.reload();
        });
        manual.appendChild(summary);
        manual.appendChild(input);
        manual.appendChild(saveBtn);
        card.appendChild(titleEl);
        card.appendChild(msgEl);
        card.appendChild(scanBtn);
        card.appendChild(manual);
        overlay.appendChild(card);
        document.body.appendChild(overlay);
    }
    // APK：首启/后端失联/换网 → 配对门（扫码主路径）。两段探活=立即+1.5s
    function pairProbe() {
        fetch('/api/health').then(function (r) { return r.json(); })
            .then(function (j) {
                if (!j || j.status !== 'ok') throw new Error('not ok');
            })
            .catch(function () {
                if (!document.querySelector('.xj3-modal-overlay')) {
                    showPairGate();
                }
            });
    }
    if (window.Capacitor) {
        pairProbe();
        setTimeout(pairProbe, 1500);
        // 桌面专属入口隐藏：截图提问（依赖桌面屏幕捕获链）
        const shotItem = document.querySelector(
            '.dock-menu-item[data-action="screenshot"]');
        if (shotItem) shotItem.hidden = true;
    }
    window.showPairGate = showPairGate;        // 设置页「连接手机」可复用
    window.parsePairingPayload = parsePairingPayload;

    // 音效引擎自持兜底（2026-10-29 穿透修复）：桌宠 DOM 物理移除时
    // desktop-pet.js 的 WebAudio 引擎随之消失——window.xiaoju3Sound 缺席
    // → 铃铛绑定代码 if (soundBtn && window.xiaoju3Sound) 永假=监听器从未
    // 挂上（真机 CDP 实锤），回复到达 ding 同亡。此处自持同款最小引擎
    //（键 xiaoju3_sound/缺省 on/ding=880+1318.5Hz 双音，与旧引擎状态兼
    // 容）；pet 引擎若回归，此兜底自动让位（window 已存在则不覆盖）。
    if (!window.xiaoju3Sound) {
        const SOUND_KEY = 'xiaoju3_sound';
        let soundCtx = null;
        function soundEnsureCtx() {
            const AC = window.AudioContext || window.webkitAudioContext;
            if (!AC) return null;        // 无 AudioContext：静默降级
            try {
                if (!soundCtx) soundCtx = new AC();
                if (soundCtx.state === 'suspended') soundCtx.resume().catch(function () {});
                return soundCtx.state === 'running' ? soundCtx : null;
            } catch (e) { return null; }
        }
        function soundTone(freq, dur, delay, type, vol) {
            const c = soundEnsureCtx();
            if (!c) return;
            try {
                const osc = c.createOscillator();
                const gain = c.createGain();
                const t0 = c.currentTime + (delay || 0);
                osc.type = type || 'sine';
                osc.frequency.value = freq;
                gain.gain.setValueAtTime(0.0001, t0);
                gain.gain.exponentialRampToValueAtTime(vol || 0.08, t0 + 0.012);
                gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
                osc.connect(gain);
                gain.connect(c.destination);
                osc.start(t0);
                osc.stop(t0 + dur + 0.03);
            } catch (e) { /* 合成失败静默：提示音绝不打断主流程 */ }
        }
        window.xiaoju3Sound = {
            enabled: function () {
                try { return (localStorage.getItem(SOUND_KEY) || 'on') !== 'off'; }
                catch (e) { return true; }
            },
            ding: function () {
                if (!this.enabled()) return;
                soundTone(880, 0.10, 0, 'sine', 0.07);
                soundTone(1318.5, 0.16, 0.09, 'sine', 0.06);
            },
            toggle: function () {
                const next = this.enabled() ? 'off' : 'on';
                try { localStorage.setItem(SOUND_KEY, next); } catch (e) {}
                return this.enabled();
            },
        };
    }

    // 音效总开关（WebAudio 引擎：桌面窗侧 desktop-pet.js 或上方自持兜底）
    const soundBtn = document.getElementById('sound-toggle');
    function refreshSoundBtn() {
        if (soundBtn && window.xiaoju3Sound) {
            soundBtn.innerHTML = window.xiaoju3Sound.enabled() ? ICON_SVGS.bell : ICON_SVGS.bellOff;
        }
    }
    if (soundBtn && window.xiaoju3Sound) {
        soundBtn.addEventListener('click', () => {
            window.xiaoju3Sound.toggle();
            refreshSoundBtn();
            showToast(window.xiaoju3Sound.enabled() ? '音效已开启' : '音效已关闭');
        });
        refreshSoundBtn();
    }

    // 自动朗读开关（任务 5，前端体验三件套）：与音效开关（🔔/🔕 提示音）
    // 相互独立——音效是回复到达提示音，朗读是 AI 回复的语音播报，键名亦
    // 区分（音效 xiaoju3_sound 在 desktop-pet.js，朗读 xiaoju3_autotts）。
    // 开启后 AI 每次回复自动朗读（复用 playMsg 既有 Edge-TTS 链路：emoji
    // 剔除 → Edge 优先 → 浏览器降级链，见下方 speakMessageEl）；关闭时仅
    // 手动点播放朗读。状态 localStorage 记忆、刷新保持，默认关闭。
    const AUTO_TTS_KEY = 'xiaoju3_autotts';
    function autoTTSEnabled() {
        try { return localStorage.getItem(AUTO_TTS_KEY) === '1'; }
        catch (e) { return false; }
    }
    function setAutoTTS(on) {
        try {
            if (on) localStorage.setItem(AUTO_TTS_KEY, '1');
            else localStorage.removeItem(AUTO_TTS_KEY);   // 默认关闭：清键即关
        } catch (e) { /* localStorage 不可用时仅本次会话生效 */ }
    }
    const autoTTSBtn = document.getElementById('auto-tts-toggle');
    function refreshAutoTTSBtn() {
        if (autoTTSBtn) autoTTSBtn.innerHTML = autoTTSEnabled() ? ICON_SVGS.volume2 : ICON_SVGS.volumeX;
    }
    if (autoTTSBtn) {
        autoTTSBtn.addEventListener('click', () => {
            const on = !autoTTSEnabled();
            setAutoTTS(on);
            refreshAutoTTSBtn();
            showToast(on ? '自动朗读已开启：AI 回复将自动播报' : '自动朗读已关闭');
        });
        refreshAutoTTSBtn();   // 载入即按 localStorage 回显（刷新保持）
    }

    // ==================== 轻提示 toast（替代 alert 占位） ====================
    let toastTimer = null;
    function showToast(text) {
        let el = document.getElementById('xiaoju3-toast');
        if (!el) {
            el = document.createElement('div');
            el.id = 'xiaoju3-toast';
            document.body.appendChild(el);
        }
        el.textContent = text;
        el.classList.add('show');
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => el.classList.remove('show'), 2000);
    }

    // ==================== 0.5 TTS 朗读 emoji 剔除（任务 7）+ 音色选择（任务 4） ====================
    // 语音引擎读不出 emoji（静音/跳读）：朗读前正则整体剔除——emoji 主体区
    //（\u{1F300}-\u{1FAFF}，肤色修饰符 1F3FB-1F3FF 亦在其中）、牌类/括号/
    // 旗帜扩展区（\u{1F000}-\u{1F2FF}）、杂项符号与装饰（\u2600-\u27BF）、
    // 箭头与技术符号（\u2B00-\u2BFF、\u2300-\u23FF）、变体选择符
    //（\uFE00-\uFE0F）、ZWJ 零宽连接符（\u200D，emoji 组合序列）、键帽
    // 组合符（\u20E3）与标签变体（\u{E0020}-\u{E007F}）。标点不在任何
    // 区间内，保留作自然停顿；剔除后连续空白折叠为一个空格。
    const TTS_EMOJI_RE = /[\u{1F300}-\u{1FAFF}\u{1F000}-\u{1F2FF}\u2600-\u27BF\u2B00-\u2BFF\u2300-\u23FF\uFE00-\uFE0F\u200D\u20E3\u{E0020}-\u{E007F}]/gu;
    function stripEmojiForTTS(text) {
        return String(text == null ? '' : text)
            .replace(TTS_EMOJI_RE, '')     // emoji/修饰符/ZWJ 序列整体剔除
            .replace(/\s+/g, ' ')          // 连续空白折叠为一个空格
            .trim();
    }

    // 朗读音色回退链：localStorage(xiaoju3_tts_voice) → /api/status 下发的
    // tts_voice（后端 .env TTS_VOICE，localStorage 为空时采用并写回）→
    // getVoices() 首个中文女声（name 含女性特征词）→ 首个 zh 音色 →
    // 引擎默认音色（不设 utter.voice）。
    const TTS_VOICE_KEY = 'xiaoju3_tts_voice';
    // 女性特征词（zh 音色 name 命中其一即视为女声，大小写不敏感）
    const TTS_FEMALE_HINTS = ['晓晓', '小艺', '悦', 'female', 'Xiaoxiao'];
    // /api/status 下发的 tts_voice（空串表示后端未配置）
    let backendTTSVoice = '';

    function getStoredTTSVoiceName() {
        try { return localStorage.getItem(TTS_VOICE_KEY); } catch (e) { return null; }
    }

    // zh 音色列表（lang 以 zh 开头，兼容 zh-CN / zh-Hans-CN 等写法）
    function listZhVoices() {
        const voices = (window.speechSynthesis && window.speechSynthesis.getVoices()) || [];
        return voices.filter(v => /^zh/i.test(String(v.lang || '')));
    }

    function isFemaleZhVoice(voice) {
        const name = String((voice && voice.name) || '').toLowerCase();
        return TTS_FEMALE_HINTS.some(hint => name.indexOf(hint.toLowerCase()) !== -1);
    }

    // 按回退链解析当前朗读音色；返回 null 表示交给引擎默认音色
    function pickTTSVoice() {
        const zhVoices = listZhVoices();
        const wanted = getStoredTTSVoiceName() || backendTTSVoice;
        if (wanted) {
            const all = (window.speechSynthesis && window.speechSynthesis.getVoices()) || [];
            const hit = zhVoices.find(v => v.name === wanted) ||
                all.find(v => v.name === wanted);
            if (hit) return hit;                    // 用户/后端指定且当前可用
        }
        if (!zhVoices.length) return null;          // 无 zh 音色：默认音色兜底
        return zhVoices.find(isFemaleZhVoice) || zhVoices[0];   // 首个中文女声 → 首个 zh
    }

    // /api/status 下发 tts_voice 的采用与写回（仅 localStorage 为空时接管；
    // 同值轮询直接跳过，避免每 2s 重复重建下拉）
    function adoptBackendTTSVoice(val) {
        if (typeof val !== 'string' || !val || backendTTSVoice === val) return;
        backendTTSVoice = val;
        if (!getStoredTTSVoiceName()) {
            try { localStorage.setItem(TTS_VOICE_KEY, val); } catch (e) { /* 忽略 */ }
        }
        refreshVoiceSelector();
    }

    // ==================== 0.55 Edge-TTS 播放链路（后端 /api/tts，组 M4 契约） ====================
    // 契约钉死：POST /api/tts body {text, voice} → 200 返回 audio/mpeg 音频流
    // （blob 直接播放）或 4xx/5xx JSON {error}。voice 缺省时后端走默认音色。
    // Edge 音色常量表：与后端 xiaoju3_dashboard.EDGE_VOICES 口径一致（voice id
    // 必须逐字相同，label 为中文说明）；首个为后端默认音色（晓晓）。
    const EDGE_TTS_VOICES = [
        { name: 'zh-CN-XiaoxiaoNeural', label: '晓晓-温柔女声' },
        { name: 'zh-CN-XiaoyiNeural',   label: '晓伊-活泼女声' },
        { name: 'zh-CN-XiaomoNeural',   label: '晓墨-阳光女声' },
        { name: 'zh-CN-XiaoqiuNeural',  label: '晓秋-知性女声' },
    ];

    // localStorage 键值协议（键沿用 xiaoju3_tts_voice，测试锁定）：
    // ① 值为 EDGE_TTS_VOICES 中的音色名（如 zh-CN-XiaoxiaoNeural）→ Edge 链：
    //    /api/tts 的 voice 参数即用该值；
    // ② 值含"浏览器"字样（浏览器项写入的哨兵值 '浏览器TTS（降级）'——真值
    //    可阻止 adoptBackendTTSVoice 在 2s 轮询中回填覆盖用户选择）、值含
    //    浏览器音色名（如"Google 普通话"）等非 Edge 音色名、或两者皆空
    //    → 浏览器 TTS 降级链（既有回退链语义零回退）。
    // /api/status 下发的 tts_voice（.env TTS_VOICE）仍经上方 adoptBackendTTSVoice
    // 在 localStorage 为空时写回——后端配置 Edge 音色名即成为 Edge 初始默认。
    function isEdgeTTSVoice(name) {
        return EDGE_TTS_VOICES.some(v => v.name === name);
    }

    // 朗读链路解析：Edge 优先（记忆值为 Edge 音色名），否则浏览器降级链
    function resolveTTSMode() {
        const stored = getStoredTTSVoiceName() || backendTTSVoice;
        if (stored && isEdgeTTSVoice(stored)) return { mode: 'edge', voice: stored };
        // 协议口径：browser 分支返回音色"名称字符串"（SpeechSynthesisVoice
        // 对象则解包 .name；playMsg 浏览器路径不经 plan.voice，自行重挑）
        var v = pickTTSVoice();
        return { mode: 'browser', voice: (v && v.name) ? v.name : v };
    }

    // 音色下拉菜单（纯 JS 动态构建，不改 index.html）：挂在聊天头部工具区。
    // 升级为 Edge 音色列表（/api/tts 云端合成，值 = Edge 音色名）+ "浏览器
    // TTS（降级）"项（值 = ''，走既有回退链）；切换即写 localStorage；
    // 选中项按上方键值协议回显。
    let ttsVoiceSelect = null;
    function refreshVoiceSelector() {
        const actions = document.querySelector('.chat-header .header-actions');
        if (!actions) return;
        if (!ttsVoiceSelect) {
            ttsVoiceSelect = document.createElement('select');
            ttsVoiceSelect.id = 'tts-voice-select';
            ttsVoiceSelect.title = '朗读音色（Edge 云端合成 / 浏览器降级）';
            ttsVoiceSelect.style.cssText =
                'max-width: 140px; font-size: 12px; padding: 3px 4px;' +
                'border: 1px solid var(--color-border); border-radius: var(--radius-tool);' +
                'background: var(--color-card); color: var(--color-text-secondary);' +
                'outline: none; cursor: pointer;';
            ttsVoiceSelect.addEventListener('change', function () {
                const name = ttsVoiceSelect.value;
                try {
                    if (name) {
                        localStorage.setItem(TTS_VOICE_KEY, name);   // Edge 音色名（协议①）
                    } else {
                        // 空值兜底分支（正常情况下浏览器项 value 直接含"浏览
                        // 器"字样，走不到这里）：清除记忆交回退链
                        localStorage.removeItem(TTS_VOICE_KEY);
                    }
                } catch (e) { /* localStorage 不可用时仅本次会话生效 */ }
                showToast(name && name.indexOf('浏览器') === -1
                                ? '朗读音色已切换：' + name
                                : '朗读音色：浏览器 TTS（降级）');
            });
            actions.prepend(ttsVoiceSelect);
        }
        const zhVoices = listZhVoices();
        const browserVoice = pickTTSVoice();   // 降级链解析照常（回退链语义零回退）
        ttsVoiceSelect.innerHTML = '';
        // Edge 音色组：值 = Edge 音色名（协议①，/api/tts 携带 voice 参数）
        EDGE_TTS_VOICES.forEach(v => {
            const opt = document.createElement('option');
            opt.value = v.name;
            opt.textContent = v.label + '（Edge）';
            ttsVoiceSelect.appendChild(opt);
        });
        // 浏览器降级项：值含"浏览器"字样（协议②哨兵值，真值可阻断
        // adoptBackendTTSVoice 回填；title 提示降级后实际使用的音色）
        const browserOpt = document.createElement('option');
        browserOpt.value = '浏览器TTS（降级）';
        browserOpt.textContent = '浏览器 TTS（降级）';
        browserOpt.title = browserVoice
            ? '降级音色：' + browserVoice.name
            : '浏览器引擎默认音色（当前 ' + zhVoices.length + ' 个中文音色可用）';
        ttsVoiceSelect.appendChild(browserOpt);
        // 选中项回显：Edge 音色按名回显；浏览器链路（哨兵值/浏览器音色名/空）
        // 回落"浏览器 TTS（降级）"项
        const storedVoice = getStoredTTSVoiceName() || backendTTSVoice;
        ttsVoiceSelect.value = isEdgeTTSVoice(storedVoice)
            ? storedVoice : '浏览器TTS（降级）';
    }

    if (window.speechSynthesis) {
        refreshVoiceSelector();   // 首次构建（部分引擎同步即可列出音色）
        // 音色列表常异步到达：voiceschanged 后重建下拉（addEventListener 与
        // onvoiceschanged 双保险，重建幂等）
        if (typeof window.speechSynthesis.addEventListener === 'function') {
            window.speechSynthesis.addEventListener('voiceschanged', refreshVoiceSelector);
        }
        window.speechSynthesis.onvoiceschanged = refreshVoiceSelector;
    }

    // ==================== 1. 定时请求后端系统状态（2 秒轮询） ====================

    // ==================== 1a. 进度条三档变色（尾巴 H） ====================
    // CPU 与内存各自独立判定同一套阈值：<60 绿 / 60–85 黄 / >85 红。
    // 阈值集中常量，后续调整只改这里；颜色同步落在 .bar-* 类与内联样式。
    const BAR_THRESHOLDS = { mid: 60, high: 85 };
    const BAR_COLORS = { low: '#2fa24c', mid: '#eab308', high: '#e0433f' };

    function barLevel(percent) {
        if (percent > BAR_THRESHOLDS.high) return 'high';
        if (percent >= BAR_THRESHOLDS.mid) return 'mid';
        return 'low';
    }

    function applyBar(barEl, percent) {
        if (!barEl) return;
        const level = barLevel(Math.max(0, Math.min(100, Number(percent) || 0)));
        barEl.style.width = percent + '%';
        barEl.style.backgroundColor = BAR_COLORS[level];
        barEl.classList.remove('bar-low', 'bar-mid', 'bar-high');
        barEl.classList.add('bar-' + level);
    }

    function markConnecting() {
        // 失败加载态（2026-10-04 启动优化拍板② B/C 小补）：状态/待办拉取
        // 失败（多为轮询竞态或服务冷启动瞬间）→ UI 显"连接中…"而非静止
        // 旧值像"没数据"；下一轮轮询自动恢复（fetchStatus 2s / loadTodos
        // 30s），不加重试逻辑
        const cpuText = document.getElementById('cpu-text');
        const memText = document.getElementById('mem-text');
        if (cpuText) cpuText.textContent = '连接中…';
        if (memText) memText.textContent = '连接中…';
        const listEl = document.getElementById('todos-list');
        if (listEl) listEl.innerHTML = '<li class="todos-empty">连接中…</li>';
    }

    function fetchStatus() {
        fetch('/api/status')
            .then(res => res.json())
            .then(res => {
                if (res.code === 200) {
                    const d = res.data;
                    // 版本源（#264 B2c 收尾：header 版本号已删，版本只进
                    // VERSION_STATE 供关于卡使用；/api/status 能力保留）
                    if (d.version) {
                        window.__xiaoju3Version = String(d.version);
                        // #UI修复 2026-10-13：页脚版本号（连点 7 次=开发者
                        // 暗入口第二触发点）
                        const fv = document.getElementById('footer-version');
                        if (fv) fv.textContent =
                            'V' + String(d.version);
                    }
                    const cpuText = document.getElementById('cpu-text');
                    const cpuBar = document.getElementById('cpu-bar');
                    if (cpuText && cpuBar) {
                        cpuText.textContent = d.cpu + '%';
                        applyBar(cpuBar, d.cpu);   // 尾巴 H：三档变色
                    }

                    const memText = document.getElementById('mem-text');
                    const memBar = document.getElementById('mem-bar');
                    if (memText && memBar) {
                        memText.textContent = (d.mem_used != null
                            ? d.mem_used + 'GB / ' + d.mem_total + 'GB ('
                              + d.memory + '%)'
                            : d.memory + '%');
                        applyBar(memBar, d.memory);   // 尾巴 H：内存独立三档变色
                    }

                    // 多磁盘（UI 三期队长方案）：disks[] 驱动单行+▼切换
                    window.__disks = Array.isArray(d.disks) ? d.disks : [];
                    if (window.__diskSel == null
                        || window.__diskSel >= window.__disks.length) {
                        window.__diskSel = 0;   // 默认首盘（C:）
                    }
                    window.__updateDiskRow();
                    // 菜单仅在「用户开着」时刷新内容——每 2s 无条件重渲染
                    // 会把用户刚关掉的菜单又顶开（2026-10-26 真浏览器实测抓到）
                    var __dm = document.getElementById('disk-menu');
                    if (__dm && !__dm.hidden) window.__renderDiskMenu();
                    const batRow = document.getElementById('battery-row');
                    if (batRow) {
                        if (d.battery) {
                            batRow.hidden = false;
                            const bt = document.getElementById('battery-text');
                            const bb = document.getElementById('battery-bar');
                            if (bt) bt.textContent = d.battery.percent + '%'
                                + (d.battery.plugged ? ' ⚡' : '');
                            if (bb) bb.style.width = d.battery.percent + '%';
                        } else {
                            batRow.hidden = true;   // 台式机/无电池：整行隐藏
                        }
                    }

                    const tempText = document.getElementById('temp-text');
                    if (tempText) {
                        tempText.textContent = 'GPU '
                            + (typeof d.temperature === 'number'
                               ? d.temperature + '°C'
                               : (d.temperature || 'N/A'));
                    }

                    // TTS 音色回退链第二级：后端 .env TTS_VOICE（payload 契约
                    // 字段 tts_voice；localStorage 为空时采用并写回）
                    adoptBackendTTSVoice(d.tts_voice);

                    // ✍️ 创作者署名（2026-10-02）：不再写入页面标题/顶栏
                    //（2026-10-02 用户口径：标题栏隐藏"为 XUN 而建"，保持
                    // "小橘3号 · 控制台" 原样）；/creator 命令与启动日志
                    // 署名不受影响。creator 字段仍随 /api/status 下发。
                }
            })
            .catch(err => {
                console.error('获取系统状态失败', err);
                markConnecting();
            });
    }

    fetchStatus();
    setInterval(fetchStatus, 2000);



    // ==================== 1b. 待办卡片（2026-10-04 待办提取，设计稿 §6） ====================
    // 数据=GET /api/todos；30 秒低频轮询（待办非实时数据）+ 标完成后即时刷新；
    // last_job.running 时卡片顶显示"⏳ 正在阅读链接…"（提取在后台线程进行）。
    const TODOS_REFRESH_MS = 30000;

    let todoEditing = false;   // 尾巴 F：优先级编辑模式（默认锁定 pill）
    let gearEl = null;
    // #239 待办说明折叠：展开态本会话 JS 记忆（不持久化，默认每次收起）
    let expandedNotes = [];

    // 尾巴 I（改服务端承载，2026-10-04）：WebView2 InPrivate 下 localStorage
    // 跨启动即焚（同 first_run 方案 C 前科）→ 折叠状态由 GET /api/todos 下发
    // （服务端 todo_ui_state.json），切换经 POST /api/todos/collapsed_groups
    let collapsedGroups = [];   // 最近一次服务端下发（toggle 时基于它切换）

    function toggleGroup(pr) {
        const i = collapsedGroups.indexOf(pr);
        if (i >= 0) collapsedGroups.splice(i, 1);
        else collapsedGroups.push(pr);
        fetch('/api/todos/collapsed_groups', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ collapsed_groups: collapsedGroups })
        }).then(() => loadTodos())
          .catch(err => console.error('保存折叠状态失败', err));
    }

    function loadTodos() {
        fetch('/api/todos')
            .then(res => res.json())
            .then(res => {
                if (res.code === 200) renderTodos(res.data);
            })
            .catch(err => {
                console.error('获取待办失败', err);
                markConnecting();
            });
    }

    function renderTodos(data) {
        const listEl = document.getElementById('todos-list');
        const countEl = document.getElementById('todos-count-text');
        const jobEl = document.getElementById('todos-job-line');
        if (!listEl) return;
        if (countEl) countEl.textContent = data.pending_count ? `(${data.pending_count})` : '';
        if (gearEl) {
            gearEl.innerHTML = ICON_SVGS.settings;           // 尾巴 F2：单一图标（矢量齿轮，2026-10-29 去 Emoji）
            gearEl.classList.toggle('editing', todoEditing);  // 编辑态橙色高亮
        }
        if (jobEl) {
            const job = data.last_job;
            if (job && job.state === 'running') {
                jobEl.textContent = '⏳ 正在阅读链接…';
                jobEl.hidden = false;
            } else if (job && job.state === 'failed') {
                jobEl.textContent = '❌ 上次提取失败，可重新发送链接重试';
                jobEl.hidden = false;
            } else {
                jobEl.hidden = true;
            }
        }
        // 尾巴 1+C 精确版（2026-10-04）：P0/P1/P2 分区视图——各区带标题行
        // （── Px ──），空分区不显示；pill 点即改后 loadTodos 全量刷新 =
        // 条目实时移动到对应分区；分区内沿用 items 既有顺序（id 倒序）
        if (Array.isArray(data.collapsed_groups)) {
            collapsedGroups = data.collapsed_groups;   // 尾巴 I：服务端下发折叠状态
        }
        const items = data.todos;
        if (!items.length) {
            listEl.innerHTML = '<li class="todos-empty">暂无待办</li>';
            return;
        }
        // 尾巴 C 扩展修复（2026-10-04）：六档字典——旧三档初始化遇 P3+ 条目
        // 时 byPriority[pr] 为 undefined，分组循环读 .length 即 TypeError，
        // renderTodos 整体中断（卡片"暂无待办"+ 齿轮点击视觉失效的根因）
        const byPriority = { P0: [], P1: [], P2: [], P3: [], P4: [], P5: [] };
        items.forEach(t => {
            // 防再犯（2026-10-05）：priority 不在六档白名单时原逻辑静默回退
            // P1 组，脏数据伪装成正常条目（#242/#243 content↔priority 颠倒
            // 即此相——文字 P3/标签 P1）。缺省空值走 || 'P1' 不算非法，不警告
            // 时间老化（2026-10-07）：分组键用生效档 effective_priority
            // （服务端 COALESCE，未老化=原档）；"↑已升"标记在条目行渲染
            const eff = t.effective_priority || t.priority || 'P1';
            if (t.priority && !byPriority[eff]) {
                console.warn(`[todos] 非法 priority: "${eff}"（id=${t.id}），已回退至 P1 组`);
            }
            (byPriority[eff] || byPriority.P1).push(t);
        });
        let html = '';
        // #351 一期（2026-10-25）：侧栏紧凑视图——非编辑模式跨组只显示
        // 未完成前 5 条（P0 置顶天然成立：组序即优先级序），超出收进
        // "还有 X 项"尾行，防把左栏撑爆；编辑模式全量（改档需看全）。
        const pendingTotal = items.filter(t => t.status !== 'done').length;
        const compact = !todoEditing && pendingTotal > 5;
        let compactQuota = 5;
        let compactHidden = 0;
        for (const pr of ['P0', 'P1', 'P2', 'P3', 'P4', 'P5']) {
            const group = byPriority[pr] || [];   // 防御兜底：未知档位不崩
            if (!group.length) continue;   // 空分区不显示
            // 尾巴 I：分区可折叠——标题显示条数与箭头，折叠分区不输出条目
            const collapsed = collapsedGroups.includes(pr);
            const arrow = collapsed ? '▸' : '▾';
            html += `<li class="todo-group-title" data-pr="${pr}" title="点击折叠/展开">` +
                `${arrow} ── ${pr} ── (${group.length})</li>`;
            if (collapsed) continue;
            // 紧凑视图：本组只取未完成条目按剩余配额截取
            let groupRows = group;
            if (compact) {
                const pendingRows = group.filter(t => t.status !== 'done');
                const take = pendingRows.slice(0, Math.max(0, compactQuota));
                compactHidden += pendingRows.length - take.length;
                compactQuota -= take.length;
                groupRows = take;
            }
            html += groupRows.map(t => {
                const doneCls = t.status === 'done' ? ' done' : '';
                const checked = t.status === 'done' ? ' checked' : '';
                // 尾巴 F 改（用户精确要求）：锁定时 pills 完全不渲染（隐藏而非灰显）
            // 尾巴 C 扩展（用户拍板）：优先级下拉选择器——编辑态原生 select
            // 六项（P0-P5，可上下滚动），选择即 POST priority；锁定态只读
            // 徽标显示当前值（不可改）
            const prOptions = ['P0', 'P1', 'P2', 'P3', 'P4', 'P5'].map(p =>
                `<option value="${p}"${p === pr ? ' selected' : ''}>${p}</option>`).join('');
            const prControl = todoEditing
                ? `<select class="todo-pr-select" title="优先级">${prOptions}</select>`
                : `<span class="todo-pr-badge${pr === 'P0' ? ' todo-pr-p0' : ''}" title="点齿轮图标进入编辑模式后可改">${pr}</span>`;
            // #238：垃圾桶仅对已完成项渲染（pending 无删除入口）
            const delBtn = t.status === 'done'
                ? `<button class="todo-del" data-id="${t.id}" title="删除这条已完成待办" style="display:inline-flex;align-items:center">${ICON_SVGS.trash}</button>`
                : '';
            // #239 待办说明折叠（2026-10-05）：note 非空 → 主任务下渲染
            // "淡淡说明"行（默认收起，▸/▾ 切换，本会话 JS 记忆展开态）；
            // 编辑模式下说明行变 textarea + 保存（POST /api/todos/<id>/note）
            const note = (t.note || '').trim();
            const expanded = expandedNotes.includes(t.id);
            let noteHtml = '';
            if (note || todoEditing) {
                if (todoEditing) {
                    noteHtml = `<div class="todo-item" style="padding:0 4px 4px 20px;">` +
                        `<textarea class="todo-note-edit" data-id="${t.id}">${escapeHtml(note)}</textarea>` +
                        `<button class="todo-note-save" data-id="${t.id}" title="保存说明">保存</button></div>`;
                } else if (note) {
                    const arrowN = expanded ? '▾' : '▸';
                    noteHtml = `<div class="todo-item" style="padding:0 4px 4px 20px;">` +
                        `<span class="todo-note-toggle" data-id="${t.id}" title="展开/收起说明">${arrowN}</span>` +
                        (expanded ? `<div class="todo-note">${escapeHtml(note)}</div>` : '') +
                        `</div>`;
                }
            }
            // 时间老化（2026-10-07 拍板②）："↑已升"轻量标记——生效档≠原档
            // 时渲染，悬浮 title 显示 原档 → 现档
            const agedBadge = (t.effective_priority && t.effective_priority !== t.priority)
                ? `<span class="todo-aged" title="时间老化：${t.priority} → ${t.effective_priority}">↑已升</span> `
                : '';
            const todoTime = (t.created_at || '').slice(11, 16);   // HH:MM
            return `<li class="todo-item${doneCls}" data-id="${t.id}">` +
                    `<input type="checkbox" class="todo-check"${checked} title="勾选=完成，取消=恢复">` +
                    `${agedBadge}<span class="todo-text">${escapeHtml(t.content)}</span>` +
                    (todoTime ? `<span class="todo-time">${todoTime}</span>` : '') +
                    `${prControl}${delBtn}</li>` + noteHtml;
            }).join('');
        }
        // 紧凑视图尾行：被收起的未完成条目计数（点击 ⚙️ 进编辑模式查看全部）
        if (compact && compactHidden > 0) {
            html += `<li class="todo-more" title="点齿轮图标进入编辑模式查看全部">还有 ${compactHidden} 项待办…</li>`;
        }
        listEl.innerHTML = html;
    }

    gearEl = document.getElementById('todos-edit-gear');
    if (gearEl) {
        gearEl.addEventListener('click', function () {
            todoEditing = !todoEditing;
            loadTodos();   // 重渲染使 pill 锁定/解锁立即生效
        });
    }

    const todosListEl = document.getElementById('todos-list');
    if (todosListEl) {
        // 尾巴 I：分区标题点击 → 折叠/展开（click 事件——标题无值变化，
        // change 永不触发；v12 曾误放 change 监听器内成死代码，已纠）
        todosListEl.addEventListener('click', function (ev) {
            const title = ev.target.closest('li.todo-group-title');
            if (title) {
                toggleGroup(title.dataset.pr);
                loadTodos();
                return;
            }
            // #239：说明折叠切换（▸/▾）
            const toggle = ev.target.closest('span.todo-note-toggle');
            if (toggle) {
                const tid = parseInt(toggle.dataset.id, 10);
                const i = expandedNotes.indexOf(tid);
                if (i >= 0) expandedNotes.splice(i, 1);
                else expandedNotes.push(tid);
                loadTodos();
                return;
            }
            // #239：编辑模式说明保存
            const saveBtn = ev.target.closest('button.todo-note-save');
            if (saveBtn) {
                const tid = parseInt(saveBtn.dataset.id, 10);
                const box = todosListEl.querySelector(
                    `textarea.todo-note-edit[data-id="${tid}"]`);
                if (!box) return;
                fetch(`/api/todos/${tid}/note`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ note: box.value })
                }).then(() => loadTodos())
                  .catch(err => console.error('保存待办说明失败', err));
            }
            // #238：删除单条待办（仅已完成项有入口；确认弹窗二次确认 → DELETE 硬删）
            const delBtn = ev.target.closest('button.todo-del');
            if (delBtn) {
                const tid = parseInt(delBtn.dataset.id, 10);
                showConfirm('删除已完成待办',
                    '确定删除这条已完成的待办？删除后不可恢复。',
                    function () {
                        fetch(`/api/todos/${tid}`, { method: 'DELETE' })
                            .then(() => loadTodos())
                            .catch(err => console.error('删除待办失败', err));
                    }, { confirmText: '删除' });
            }
        });
        // 复选框 + 优先级下拉：值变化类交互走 change（勾=完成/取消=恢复、
        // 下拉选优先级即改）
        todosListEl.addEventListener('change', function (ev) {
            const box = ev.target.closest('input.todo-check');
            if (box) {
                const li = box.closest('li.todo-item');
                if (!li) return;
                const action = box.checked ? 'done' : 'reopen';
                fetch(`/api/todos/${li.dataset.id}/${action}`, { method: 'POST' })
                    .then(() => loadTodos())
                    .catch(err => console.error('切换待办状态失败', err));
                return;
            }
            const sel = ev.target.closest('select.todo-pr-select');
            if (sel) {
                const li = sel.closest('li.todo-item');
                if (!li) return;
                fetch(`/api/todos/${li.dataset.id}/priority`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ priority: sel.value })
                }).then(() => loadTodos())
                  .catch(err => console.error('设置待办优先级失败', err));
            }
        });
    }

    loadTodos();
    setInterval(loadTodos, TODOS_REFRESH_MS);

    // ==================== 2. 聊天渲染辅助（历史加载与实时发送共用） ====================
    // XSS 防护（界面文档 §4.4 / §10.4 近期项）：回复文本转义后渲染，换行转 <br>
    function escapeHtml(text) {
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
    // QQ 表情渲染（网页永不显示方括号 CQ 原文，与后端 web_sanitize 同口径）：
    // ① [CQ:face,id=XX] → 对应 Emoji（经典 id 0-103 全量 + 常用扩展，与
    //    web_sanitize.CQ_FACE_EMOJI 同源同义；未收录 id 兜底通用表情，不再原样保留）
    // ② [CQ:image,...] → [表情] 占位（网页无法渲染表情包图片，且不泄露服务器本机路径）
    // ③ 其余 [CQ:...]（at/record 等 QQ 专用格式）一律剥除
    const CQ_FACE_EMOJI = {
        0: '😊', 1: '😒', 2: '😍', 3: '😔', 4: '😎', 5: '😢', 6: '😊', 7: '🤫',
        8: '😴', 9: '😭', 10: '😅', 11: '😠', 12: '😜', 13: '😁', 14: '😄', 15: '😰',
        16: '😝', 17: '🤔', 18: '😪', 19: '🤮', 20: '🤭', 21: '😘', 22: '😤', 23: '😖',
        24: '😨', 25: '🥱', 26: '😵', 27: '🤐', 28: '😆', 29: '🙃', 30: '💪', 31: '🤬',
        32: '🙈', 33: '🤫', 34: '💫', 35: '😫', 36: '😩', 37: '🤗', 38: '😱', 39: '🥺',
        40: '😤', 41: '👃', 42: '👏', 43: '😬', 44: '😏', 45: '😤', 46: '🐱', 47: '🥱',
        48: '🙄', 49: '🥺', 50: '😣', 51: '😈', 52: '😘', 53: '😨', 54: '🥺', 55: '🔪',
        56: '🍉', 57: '🍺', 58: '🏀', 59: '🏓', 60: '☕', 61: '🍚', 62: '🐷', 63: '👍',
        64: '👎', 65: '💋', 66: '❤️', 67: '💔', 68: '🎂', 69: '⚡', 70: '💣', 71: '🔪',
        72: '⚽', 73: '🐞', 74: '💩', 75: '🌙', 76: '🌹', 77: '🎁', 78: '🍀', 79: '👍',
        80: '👎', 81: '🤝', 82: '✌️', 83: '🙏', 84: '👉', 85: '⚡', 86: '👎', 87: '💖',
        88: '🙅', 89: '🍺', 90: '💕', 91: '😘', 92: '🕺', 93: '😰', 94: '🔄', 95: '🙇',
        96: '👀', 97: '🤝', 98: '👋', 99: '🤩', 100: '💃', 101: '🙏', 102: '☯️', 103: '☯️',
        109: '🐱', 124: '💀', 129: '🙏', 144: '🍺', 146: '🐱',
    };
    const CQ_FACE_FALLBACK = '😊';   // 未收录 face id 的兜底表情
    function renderCQFace(text) {
        return String(text)
            .replace(/\[CQ:face,id=(\d+)\]/g, function (m, id) {
                return Object.prototype.hasOwnProperty.call(CQ_FACE_EMOJI, Number(id))
                    ? CQ_FACE_EMOJI[Number(id)] : CQ_FACE_FALLBACK;
            })
            .replace(/\[CQ:image,[^\]]*\]/g, '[表情]')
            .replace(/\[CQ:[^\]]*\]/g, '');
    }
    function renderRich(text) {
        // 行内代码+粗体+标题（2026-10-28 三轮实锤：`xxx`/**bold**/### heading
        // 裸奔出戏）：转义后按序解析，零注入面
        return renderCQFace(escapeHtml(text))
            .replace(/`([^`\n]+)`/g, '<code class="md-code">$1</code>')
            .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
            .replace(/^#{1,4}\s+(.+)$/gm, '<b class="md-heading">$1</b>')
            .replace(/\n/g, '<br>');
    }

    // ==================== Markdown 表格渲染（2026-10-28，总线选股清单实锤） ====================
    // 总线选股结果/未来插件产出含 markdown 表格（|---| 特征），原 renderRich
    // 只做转义+换行 → 竖线乱码。这里把连续表格行解析成 HTML <table>，其余
    // 文本块原样 renderRich。纯转义渲染，无注入面（单元格走 escapeHtml）。
    function isTableSeparatorLine(line) {
        const t = line.trim();
        return /^\|[\s:|-]+\|$/.test(t) && t.indexOf('-') !== -1;
    }

    function isTableRowLine(line) {
        const t = line.trim();
        return t.startsWith('|') && t.endsWith('|') && t.length >= 2;
    }

    function buildTableHtml(headerCells, bodyRows) {
        const th = headerCells.map(function (c) {
            return '<th>' + escapeHtml(c.trim()) + '</th>';
        }).join('');
        const trs = bodyRows.map(function (row) {
            const tds = row.map(function (c) {
                return '<td>' + escapeHtml(c.trim()) + '</td>';
            }).join('');
            return '<tr>' + tds + '</tr>';
        }).join('');
        return '<div class="md-table-wrap"><table class="md-table">'
            + '<thead><tr>' + th + '</tr></thead>'
            + '<tbody>' + trs + '</tbody></table></div>';
    }

    function renderRichTables(text) {
        const lines = String(text || '').split('\n');
        const out = [];
        let i = 0;
        while (i < lines.length) {
            // 表块识别：当前行是表行，且下一行是 |---| 分隔行
            if (i + 1 < lines.length && isTableRowLine(lines[i])
                    && isTableSeparatorLine(lines[i + 1])) {
                const header = lines[i].trim().replace(/^\||\|$/g, '').split('|');
                i += 2;
                const bodyRows = [];
                while (i < lines.length && isTableRowLine(lines[i])) {
                    bodyRows.push(lines[i].trim().replace(/^\||\|$/g, '').split('|'));
                    i += 1;
                }
                out.push(buildTableHtml(header, bodyRows));
            } else {
                out.push(renderRich(lines[i]));
                i += 1;
            }
        }
        return out.join('\n');
    }

    // ==================== 2.5 思维链（<think> 块 / 裸 [思考]/[计划] 标记）解析与折叠卡片 ====================
    // 契约（2026-10-01 全对话强制包装口径）：brain.smart_ask 对所有自然语言
    // 回复一律包装 <think>...</think> 块——工具流程用原生 [思考]/[计划] 或
    // 按工具名生成的占位符，普通闲聊（无工具调用）注入"[思考] 正在理解你
    // 的意图..."默认占位符；渲染入口仅由 think !== null 守卫，正文为自然
    // 语言或占位符都出卡。裸标记扫描保留作纵深防御：万一仍有旁路/旧版
    // 后端漏出裸的 [思考]/[计划]/[行动] 文本，统一入口 splitThinkBlock 做
    // 两段解析，两种形态（<think> 包装 / 裸标记）收敛到同一张折叠卡片：
    // ① <think> 包装块提取（非锚定正则 + 循环剔块；正文只保留最后一个
    //    </think> 之后的部分，块前杂散字符丢弃——用户口径）；
    // ② 剩余正文裸标记扫描：[思考]/[计划] 段落并入思考卡内容并从正文剥离；
    //    [行动] 标记与其后的单行 JSON 工具载荷（模型过程输出）一并剥离，
    //    正文只留最终自然语言回复；剥离后正文为空时显示"（操作已执行）"占位。
    // 非锚定匹配（串内任意位置，非贪婪到第一个闭合标签）：即使净化/表情转换
    // 等环节日后在块前插入了任何字符，只要 reply 含 <think> 块就必定渲染卡片，
    // 不因锚定串首而静默漏卡。
    const THINK_BLOCK_RE = /<think>([\s\S]*?)<\/think>/;

    // 裸 [思考] 段（协议硬性要求半角方括号标记，全角变体仅后端兼容）：内容
    // 跨行（[\s\S] 非贪婪），止于下一个 [计划]/[行动] 标记或串尾——前瞻零
    // 消费，标记本身留给下一段扫描/[行动] 剥离；普通聊天提到"思考"二字
    // （无方括号标记）不命中，不误剥离。
    const BARE_THINK_RE = /(\[思考\][\s\S]*?)(?=\[行动\]|\[计划\]|$)/;
    // 裸 [计划] 段：止于 [行动] 标记或串尾（边界口径同上）。
    const BARE_PLAN_RE = /(\[计划\][\s\S]*?)(?=\[行动\]|$)/;
    // [行动] 剥离：标记本身一律剥离；其后若跟以 { 起头的行内 JSON 工具载荷
    // （prompts 协议硬性口径"[行动] 行必须且只能是一行合法 JSON"），载荷同样
    // 剥离（[^\n] 不跨行，载荷之后各行的最终自然语言回复保留）；载荷不是
    // JSON 形态时只剥标记、保留其后文本，防误伤普通聊天里合法出现的
    // "[行动]"字样。
    const BARE_ACTION_RE = /\s*\[行动\](?:[ \t]*\{[^\n]*)?/;

    // 渲染入口先判 thinkMatch：把原始 reply 切分为 { think, body }，
    // 调用方再各自走 textContent / renderRich（先切分后转义，顺序不可反）。
    // F4 加固：函数体整体包 try/catch——任何解析异常都不影响后续消息渲染，
    // catch 记录 "CoT Render Error" 并返回安全降级值（think=已剥离出的
    // 部分或 null、body=原文），绝不让单条消息解析崩溃吞掉整轮回复。
    function splitThinkBlock(rawReply) {
        const raw = String(rawReply == null ? '' : rawReply);
        let think = null;
        let body = raw;
        try {
            // ① <think> 包装块（用户口径）：非锚定 + 循环剔块——只要 reply 含
            //    <think> 就必定出卡片，多个块全部并入同一张卡；正文只保留最后
            //    一个 </think> 之后的部分，块前杂散字符一律丢弃，思考文本绝不
            //    混进聊天正文。空 <think></think> 块同样算"有思考块"（think 为
            //    空串而非 null，与既有 think !== null 卡片判定口径一致）。
            let thinkMatch;
            while ((thinkMatch = body.match(THINK_BLOCK_RE)) !== null) {
                think = (think ? think + '\n' : '') + thinkMatch[1].trim();
                body = body.slice(thinkMatch.index + thinkMatch[0].length);
            }
            // ①-b 游离闭合标签容错（后端拼装异常可能残留不成对标签，2026-10-01
            //     用户口径）：只有闭合 </think> 时——闭合标签（含）之前的全部
            //     内容按思考处理，正文只保留最后一个 </think> 之后的部分。
            const closeIdx = body.lastIndexOf('</think>');
            if (closeIdx !== -1) {
                const before = body.slice(0, closeIdx).replace(/<\/?think>/g, '').trim();
                if (before) think = (think ? think + '\n' : '') + before;
                body = body.slice(closeIdx + '</think>'.length);
            }
            // ①-c 未配对 <think> 容错（任何位置，2026-10-01 用户口径）：成对
            //     块已在 ① 剔尽，此处残留的开头标签必无闭合（串尾截断的畸形
            //     残块）——标签及其后的截断思考内容整段并入思考卡（同孤儿
            //     口径，绝不作为正文上屏），标签前的正文保留；剥离后正文
            //     剥空由既有占位口径兜底。残留的游离 <think>/</think> 一律
            //     剥除，绝不上屏。
            const openIdx = body.indexOf('<think>');
            if (openIdx !== -1) {
                const head = body.slice(0, openIdx).trim();
                const orphan = body.slice(openIdx).replace(/<\/?think>/g, '').trim();
                if (orphan) think = (think ? think + '\n' : '') + orphan;
                body = head;
            }
            body = body.trim();

            // ② 裸 [思考]/[计划] 段落扫描：并入思考卡内容并从正文剥离
            //    （<think> 包装缺失时，裸 CoT 不再漏进聊天正文）
            const bareParts = [];
            body = body.replace(BARE_THINK_RE, function (m, seg) {
                if (seg.trim()) bareParts.push(seg.trim());
                return '';
            });
            body = body.replace(BARE_PLAN_RE, function (m, seg) {
                if (seg.trim()) bareParts.push(seg.trim());
                return '';
            });
            if (bareParts.length) {
                // 两种形态收敛到同一张卡片：<think> 内容在前，裸段按出现顺序追加
                think = (think ? think + '\n' : '') + bareParts.join('\n');
            }

            // ③ [行动] 标记与其后的行内 JSON 工具载荷剥离（模型过程输出不上屏）；
            //    正文被剥空且确有过程输出被剥离（有思考卡或剥过 [行动]）时，
            //    正文显示占位——说明本轮是纯工具动作、无自然语言收尾
            const hadAction = BARE_ACTION_RE.test(body);
            body = body.replace(BARE_ACTION_RE, '').trim();
            // 安全网：剥离一切残留游离标签（成对块已在 ① 提取，此处只兜底）
            body = body.replace(/<\/?think>/g, '').trim();
            if (think !== null) think = think.replace(/<\/?think>/g, '').trim();
            if (!body && (think !== null || hadAction)) body = '（操作已执行）';

            return { think: think, body: body };
        } catch (e) {
            // 安全降级：解析出错时 think 返回已剥离出的部分（尚无则 null、
            // 不出卡），body 回退原文，正文照常渲染
            console.error("CoT Render Error: ", e);
            return { think: think, body: raw };
        }
    }

    // 直出思维流块（2026-10-22 二轮拍板：废弃折叠卡，对标 DeepSeek）：
    // 🧠 标签行 + 灰色小号思考行直接外冒，纯静态无折叠无动画；流式态复用
    // 同一 DOM 形态（ensureThinkCard），最终/历史回放/刷新共用本构建器。
    // 全部 textContent 注入免 XSS；[思考]/[计划]/[行动] 前缀剥除不显示
    function buildThinkLiveBlock(thinkText) {
        const wrap = document.createElement('div');
        wrap.className = 'think-live';
        const label = document.createElement('div');
        label.className = 'think-live-label';
        label.textContent = '🧠 思考过程';
        wrap.appendChild(label);
        splitThinkStageLines(thinkText).forEach(function (seg) {
            const row = document.createElement('div');
            row.className = 'think-live-line';
            row.textContent = seg.text;
            wrap.appendChild(row);
        });
        return wrap;
    }

    // 深色降级兜底块（F4 加固）：思考卡片构建/插入任何环节失败时，改用
    // 纯 createElement + 内联样式的深色文本块展示思考过程（无类名依赖、
    // 不经 innerHTML），内容取思考文本前 200 字、textContent 注入免 XSS
    // ——保证思考过程任何情况下可见。
    function buildThinkFallbackBlock(thinkText) {
        const block = document.createElement('div');
        block.style.background = '#1f2937';     // 深色背景（任务规格色）
        block.style.color = '#ffffff';          // 白字
        block.style.fontSize = '13px';
        block.style.padding = '6px 10px';
        block.style.borderRadius = '10px';
        block.style.marginBottom = '5px';
        block.style.whiteSpace = 'pre-wrap';
        block.style.wordBreak = 'break-word';
        block.textContent = '🧠 思考过程：' + String(thinkText == null ? '' : thinkText).slice(0, 200);
        return block;
    }

    // 阶段标记行：[思考]/[计划]/[行动] 起始（半角方括号，与后端协议同口径）
    // 直出模式仅用于剥除前缀（行内容不再渲染徽章/缩进，二轮拍板）
    const THINK_STAGE_RE = /^\[(思考|计划|行动)\]/;

    // 把思考文本拆成逐行段：阶段标记行起新段（tag 取标记文字、text 去掉
    // 标记前缀），其余行并入当前段（保留换行，由 pre-wrap 渲染）
    function splitThinkStageLines(text) {
        const segs = [];
        let cur = null;
        String(text == null ? '' : text).split('\n').forEach(function (raw) {
            const line = String(raw).trim();
            if (!line) return;
            const m = line.match(THINK_STAGE_RE);
            if (m) {
                cur = { tag: m[1], text: line.slice(m[0].length).trim() };
                segs.push(cur);
            } else if (cur) {
                cur.text = cur.text ? cur.text + '\n' + line : line;
            } else {
                cur = { tag: '', text: line };
                segs.push(cur);
            }
        });
        return segs;
    }

    // 刷新重生成后同步思维流块：有 <think> 则重建直出块（无动画），无则移除
    // 旧块。F4 加固：插入手工 DOM 化（不依赖 before 系快捷方法）——显式父
    // 引用 + insertBefore，块位于气泡正文上方；插入失败降级为深色纯文本块。
    function syncThinkCard(msgEl, thinkText) {
        const bubble = msgEl.querySelector('.bubble-content');
        if (!bubble) return;
        const old = msgEl.querySelector('.think-live');
        if (old) old.remove();
        if (thinkText === null) return;   // 新回复没有 think 块：不插
        try {
            bubble.parentNode.insertBefore(buildThinkLiveBlock(thinkText), bubble);
        } catch (e) {
            console.error("CoT Render Error: ", e);
            // 降级兜底：深色纯文本块仍插在气泡上方，思考过程必可见
            try {
                bubble.parentNode.insertBefore(
                    buildThinkFallbackBlock(thinkText), bubble);
            } catch (fbErr) {
                console.error("CoT Render Error: ", fbErr);
            }
        }
    }

    // ==================== IM 式时间分隔（2026-10-10，问题 3） ====================
    // 连续消息只在第一条前显示时间；间隔 >5 分钟插新分隔条；格式分级
    // 今天 HH:MM / 昨天 HH:MM / MM-DD HH:MM / 跨年 YYYY-MM-DD HH:MM。
    let _lastMsgTs = null;   // 上一条消息时间（ISO 字符串或 null）

    function fmtTimeSep(ts) {
        const d = new Date(ts);
        if (isNaN(d)) return '';
        const p2 = n => String(n).padStart(2, '0');
        const hm = `${p2(d.getHours())}:${p2(d.getMinutes())}`;
        const now = new Date();
        if (d.toDateString() === now.toDateString()) return hm;
        const yest = new Date(now); yest.setDate(now.getDate() - 1);
        if (d.toDateString() === yest.toDateString()) return '昨天 ' + hm;
        const md = `${p2(d.getMonth() + 1)}-${p2(d.getDate())}`;
        if (d.getFullYear() === now.getFullYear()) return md + ' ' + hm;
        return `${d.getFullYear()}-${md} ` + hm;
    }

    function maybeTimeSeparator(ts) {
        if (!ts) { _lastMsgTs = new Date().toISOString(); return; }
        const t = new Date(ts);
        if (isNaN(t)) return;
        if (_lastMsgTs !== null) {
            const prev = new Date(_lastMsgTs);
            if (!isNaN(prev) && (t - prev) < 5 * 60 * 1000) {
                _lastMsgTs = ts; return;   // 连续消息：不插
            }
        }
        const history = document.getElementById('chat-history');
        const sep = document.createElement('div');
        sep.className = 'time-separator';
        sep.textContent = fmtTimeSep(ts);
        history.appendChild(sep);
        _lastMsgTs = ts;
    }

    function appendUserMessage(text, ts) {
        const history = document.getElementById('chat-history');
        maybeTimeSeparator(ts || new Date().toISOString());
        const userMsg = document.createElement('div');
        userMsg.className = 'message user-message';
        userMsg.textContent = text;   // textContent 注入，无 XSS 风险
        history.appendChild(userMsg);
        history.scrollTop = history.scrollHeight;
        return userMsg;
    }

    // ==================== 2.6 系统类消息统一工具栏（任务 5） ====================
    // 首条系统欢迎语与系统提示类消息（清空后的欢迎语、请求失败提示）与
    // AI 回复共用同一套工具栏行为：复制/朗读/点赞/点踩（重新生成依赖
    // dataset.prompt 原消息、转发面向会话回复，系统消息不提供这两项）。
    // 正文包进 .bubble-content，与 appendBotMessage 气泡结构同构——
    // copyText/playMsg/toggleLike/toggleDislike 全局函数零改动直接复用。
    function buildSystemMsgTools() {
        const tools = document.createElement('div');
        tools.className = 'msg-tools';
        tools.innerHTML =
            '<span class="tool-btn" onclick="copyText(this)" title="复制">' +
                '<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>' +
            '</span>' +
            '<span class="tool-btn" onclick="playMsg(this)" title="播放">' +
                '<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path></svg>' +
            '</span>' +
            '<span class="tool-btn like-btn" onclick="toggleLike(this)" title="点赞">' +
                '<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"></path></svg>' +
            '</span>' +
            '<span class="tool-btn dislike-btn" onclick="toggleDislike(this)" title="踩">' +
                '<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"></path></svg>' +
            '</span>';
        return tools;
    }

    // 给系统类消息挂统一工具栏：已有 .msg-tools（appendBotMessage 产物）
    // 直接跳过，不重复挂载；挂载后消息自带 .bubble-content，复制/朗读
    // 取到的就是纯文本正文
    function mountSystemToolbar(msgEl) {
        if (!msgEl || msgEl.querySelector('.msg-tools')) return;
        const inner = document.createElement('div');
        inner.style.cssText = 'display:flex; flex-direction:column; gap:5px;';
        const bubble = document.createElement('div');
        bubble.className = 'bubble-content';
        while (msgEl.firstChild) bubble.appendChild(msgEl.firstChild);   // 正文迁入气泡容器
        inner.appendChild(bubble);
        inner.appendChild(buildSystemMsgTools());
        msgEl.appendChild(inner);
    }

    // 首条系统欢迎语（index.html 静态节点）挂统一工具栏；appendBotMessage
    // 生成的消息自带 .msg-tools，经上方 guard 自动跳过
    document.querySelectorAll('#chat-history .message.bot-message')
        .forEach(function (m) { mountSystemToolbar(m); m.classList.add('msg-enter'); });

    // ==================== 快捷指令卡（2026-10-22 答辩微调） ====================
    // [记待办] 预填输入框并聚焦（话术已过触发词扩展全链验证，用户补内容即发）；
    // [系统自检] 消费既有 /api/health 端点 + toast 播报——零新增后端、
    // 零流式通信逻辑改动（纯前端既有接口消费）
    (function initQuickActions() {
        const quickTodo = document.getElementById('quick-todo');
        if (quickTodo) {
            quickTodo.addEventListener('click', function () {
                const input = document.getElementById('chat-input');
                if (!input) return;
                input.value = '帮我记待办：';
                input.focus();
            });
        }
        const quickCheck = document.getElementById('quick-check');
        if (quickCheck) {
            quickCheck.addEventListener('click', function () {
                fetch('/api/health')
                    .then(res => res.json())
                    .then(d => {
                        showToast(d && d.status === 'ok'
                            ? '🩺 系统自检通过：服务健康'
                            : '⚠️ 自检异常：服务状态 ' + (d && d.status || '未知'));
                    })
                    .catch(() => showToast('❌ 自检失败：服务不可达'));
            });
        }
    })();

    // ==================== 输入扩展栏（UI 一期 2026-10-25，豆包式） ====================
    // ＋ 轻量菜单（上传/截图/链接——二三期能力入口，一期占位 toast）+
    // ⚡技能/🧩插件双入口（浮层清单）+ 上下文标签条（动态渲染当前任务）。
    // 消费 GET /api/plugins（dashboard 新端点）与插件 _JOB 状态。
    (function initInputDock() {
        const menu = document.getElementById('input-dock-menu');
        const popover = document.getElementById('dock-popover');
        const plus = document.getElementById('dock-plus');
        if (!menu || !popover || !plus) return;

        function closeAll() {
            menu.hidden = true;
            popover.hidden = true;
        }
        function toggleMenu() {
            const was = menu.hidden;
            closeAll();
            menu.hidden = !was;
        }
        plus.addEventListener('click', toggleMenu);
        // 外点关闭豁免清单（2026-10-26 修复＋号/技能/插件"点击无响应"：旧版
        // 只认 .input-dock 类而 HTML 里无人带该类→按钮自己的点击也冒泡进
        // closeAll，同一次 click 内开了又关=肉眼无响应。改为显式豁免三个
        // 触发按钮+标签条+两浮层）
        document.addEventListener('click', function (ev) {
            if (!ev.target.closest('#dock-plus, #dock-skills, #dock-plugins, .context-tags-bar')
                && !ev.target.closest('.input-dock-menu')
                && !ev.target.closest('.dock-popover')) closeAll();
        });
        menu.addEventListener('click', function (ev) {
            // 技能/插件按钮自带 fetch+弹层逻辑（绑在按钮本体）——菜单关闭器
            // 跳过，防 closeAll 把异步弹出的清单又关掉
            if (ev.target.closest('#dock-skills, #dock-plugins')) return;
            const item = ev.target.closest('.dock-menu-item');
            if (!item) return;
            closeAll();
            const act = item.dataset.action;
            if (act === 'upload') {
                // UI 三期（队长纠偏 2026-10-26）：上传=附件直读上下文（非建
                // 知识库）——选择器拿绝对路径→后端解析全文挂「下一次对话」→
                // 📎 附件就绪标签，AI 直接看全文回答
                if (!window.pywebview || !window.pywebview.api) {
                    showToast('📎 上传请在桌面窗口中使用（浏览器预览不支持）');
                    return;
                }
                showToast('📎 支持 TXT/PDF/Word/Excel/代码等格式，'
                    + '请选择具体文件，不支持直接选文件夹');
                window.pywebview.api.pick_docs().then(function (r) {
                    if (!r || !r.ok) {
                        showToast('❌ ' + ((r && r.error) || '选择器打开失败'));
                        return;
                    }
                    if (!(r.paths || []).length) return;   // 用户取消：静默
                    showToast('⏳ 正在读取 ' + r.paths.length + ' 个文件…');
                    fetch('/api/doc_upload', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ paths: r.paths })
                    })
                        .then(res => res.json())
                        .then(d => {
                            if (d.code === 200 && (d.data || {}).ok_count > 0) {
                                showAttachBar((d.data.results || [])
                                    .filter(function (x) { return x.ok; })
                                    .map(function (x) {
                                        return {
                                            name: (x.path || '').split(/[\/]/).pop(),
                                            size: x.size || ''
                                        };
                                    }));
                                showToast('📎 文件已就绪，直接提问即可');
                            } else if (d.code === 200) {
                                showToast('❌ 读取失败：'
                                    + (((d.data || {}).results || [])[0] || {}).message);
                            } else {
                                showToast('❌ ' + (d.error || '上传失败'));
                            }
                        })
                        .catch(() => showToast('❌ 上传服务不可达'));
                }).catch(function (e) { showToast('❌ ' + e); });
            } else if (act === 'screenshot') {
                // UI 三期切片 b（2026-10-26）：js_api 隐藏主窗→冻结帧划选→
                // PNG 暂存→📷 条就绪→发送时 GLM-4V-Flash 看图回答
                if (!window.pywebview || !window.pywebview.api) {
                    showToast('📷 截图请在桌面窗口中使用（浏览器预览不支持）');
                    return;
                }
                showToast('📷 划选截图：主窗暂隐，拖红框，Esc 取消');
                window.pywebview.api.snip_now().then(function (r) {
                    if (!r || !r.ok) {
                        var msg = (r && r.error) || '截图失败';
                        showToast(msg.indexOf('❌') === 0 ? msg : '❌ ' + msg);
                        return;
                    }
                    if (!r.path) return;   // 用户取消：静默
                    fetch('/api/screenshot/stage', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ path: r.path })
                    })
                        .then(res => res.json())
                        .then(d => {
                            if (d.code === 200) {
                                showShotBar(d.data.size || '');
                                showToast('📷 截图已就绪，输入问题后发送');
                            } else {
                                showToast('❌ ' + (d.error || '截图暂存失败'));
                            }
                        })
                        .catch(() => showToast('❌ 截图服务不可达'));
                }).catch(function (e) { showToast('❌ ' + e); });
            } else if (act === 'link') {
                const input = document.getElementById('chat-input');
                if (input) { input.value = '总结这个视频 '; input.focus(); }
            }
        });

        // ⚡技能 / 🧩插件 浮层（消费 /api/plugins）
        function showPopover(title, rowsHtml) {
            popover.innerHTML = '<h4>' + title + '</h4>' + rowsHtml;
            closeAll();
            popover.hidden = false;
        }
        // 📎 附件就绪标签（上传→附件直读上下文；随下一次发送消费，发即隐）。
        // v0 芯片形态（2026-10-26 像素级对齐）：白底细边框微阴影圆角小方块，
        // 文件名+大小+右上角 ✕；显隐用 hidden 属性+CSS [hidden] 补丁
        const attachBar = document.getElementById('attach-bar');
        var DOC_SVG = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none"'
            + ' stroke="currentColor" stroke-width="2" stroke-linecap="round"'
            + ' stroke-linejoin="round"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0'
            + ' 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v4a2 2 0 0 0 2 2h6"/></svg>';
        var CAM_SVG = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none"'
            + ' stroke="currentColor" stroke-width="2" stroke-linecap="round"'
            + ' stroke-linejoin="round"><path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2'
            + ' 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-1.5-3Z"/>'
            + '<circle cx="12" cy="13" r="3"/></svg>';
        function showAttachBar(items) {
            if (!attachBar || !(items || []).length) return;
            var chips = items.map(function (f) {
                return '<span class="attach-chip">'
                    + '<span class="attach-chip-ico">' + DOC_SVG + '</span>'
                    + '<span class="attach-chip-body">'
                    + '<span class="attach-chip-name">' + escapeHtml(f.name) + '</span>'
                    + '<span class="attach-chip-size">' + escapeHtml(f.size || '') + '</span>'
                    + '</span>'
                    + '<button class="attach-clear" title="移除附件" style="display:inline-flex;align-items:center">' + ICON_SVGS.x + '</button>'
                    + '</span>';
            }).join('');
            attachBar.innerHTML = '<div class="attach-chip-row">' + chips + '</div>'
                + '<div class="attach-ready">📎 文件已就绪（可以直接提问）</div>';
            attachBar.removeAttribute('hidden');
            attachBar.querySelector('.attach-clear').addEventListener(
                'click', function () {
                    fetch('/api/doc_attach/clear', { method: 'POST' })
                        .catch(() => {});
                    attachBar.setAttribute('hidden', '');
                });
        }
        function hideAttachBar() {
            if (attachBar) attachBar.setAttribute('hidden', '');
        }
        window.__xj3HideAttach = function () {
            hideAttachBar();
            if (window.__xj3HideShot) window.__xj3HideShot();
        };   // 发送流钩子（Stream/Legacy 首行调用）：文本附件+截图都随发送消费
        // 幽灵附件态封死（2026-10-26 阻断 Bug②，真机实锤：22:16 传书未发消息
        // →22:21 刷新页面芯片即焚→22:21:51 纯链路测试被注入 5 分钟前的 2500 字
        // 小说全文）。芯片是附件就绪的唯一信标：刷新/重开窗口后芯片必空，
        // 后端滞留的 _DOC_ATTACH/_SHOT_ATTACH 必须同步清空——页面加载即对表。
        fetch('/api/doc_attach/clear', { method: 'POST' }).catch(function () {});
        fetch('/api/screenshot/clear', { method: 'POST' }).catch(function () {});
        // 发送按钮置灰联动（2026-10-26 阻断 Bug①）：输入框空→disabled 置灰
        // 不可点，有字→蓝色可点；发送清空后经 __xj3SyncSendBtn 同步回灰。
        // Enter 键入口走 sendMessage 内空文本守卫，与按钮态同一判定源（trim）。
        var sendBtn = document.getElementById('send-btn');
        var chatInput = document.getElementById('chat-input');
        function syncSendBtn() {
            if (!sendBtn || !chatInput) return;
            sendBtn.disabled = !((chatInput.value || '').trim());
        }
        if (sendBtn && chatInput) {
            chatInput.addEventListener('input', syncSendBtn);
            syncSendBtn();
        }
        window.__xj3SyncSendBtn = syncSendBtn;
        // 📷 截图就绪标签（复用附件条位芯片形态；发送时 GLM-4V 看图回答）
        function showShotBar(size) {
            if (!attachBar) return;
            attachBar.innerHTML = '<div class="attach-chip-row">'
                + '<span class="attach-chip">'
                + '<span class="attach-chip-ico">' + CAM_SVG + '</span>'
                + '<span class="attach-chip-body">'
                + '<span class="attach-chip-name">屏幕截图</span>'
                + '<span class="attach-chip-size">' + escapeHtml(size || '') + '</span>'
                + '</span>'
                + '<button class="attach-clear" title="移除截图" style="display:inline-flex;align-items:center">' + ICON_SVGS.x + '</button>'
                + '</span></div>'
                + '<div class="attach-ready">📷 截图已就绪（发送时 AI 直接看图回答）</div>';
            attachBar.removeAttribute('hidden');
            attachBar.querySelector('.attach-clear').addEventListener(
                'click', function () {
                    fetch('/api/screenshot/clear', { method: 'POST' })
                        .catch(() => {});
                    attachBar.setAttribute('hidden', '');
                });
        }
        window.__xj3HideShot = function () {
            if (attachBar) attachBar.setAttribute('hidden', '');
        };
        // 插件快捷指令映射（2026-10-29 队长指令：插件面板从只读列表升级
        // 为可点击入口——点一下等价于输入触发指令并自动发送，走既有总线/
        // intent_router 链；打字触发保持原样不受影响）。不在表内的插件
        // 仍为纯展示。upload 动作=复用 ＋ 菜单的文件选择流（桌面窗口）。
        const PLUGIN_QUICK_ACTIONS = {
            stock_assistant: '帮我选股',
            dice:            '掷骰子',
            video_ingest:    '提取视频内容',
            doc_ingest:      null,   // 无指令语义：整行点击=弹文件选择（原流程）
        };
        function fetchPlugins(kind) {
            fetch('/api/plugins')
                .then(res => res.json())
                .then(res => {
                    const d = (res.data || {});
                    const rows = [];
                    if (kind === 'plugins') {
                        (d.plugins || []).forEach(function (p) {
                            const qa = PLUGIN_QUICK_ACTIONS[p.name];
                            const clickable = qa !== undefined;
                            rows.push('<div class="dp-row'
                                + (clickable ? ' dp-click' : '')
                                + '" data-plugin="' + escapeHtml(p.name) + '"'
                                + (qa ? ' title="点击填入触发词：' + escapeHtml(qa)
                                    + '（可编辑后发送）"' : ' title="点击选择文件"')
                                + ' style="display:flex;align-items:center;gap:6px">'
                                + ICON_SVGS.puzzle + ' ' + escapeHtml(p.name)
                                + ' <span class="dp-sub">v' + escapeHtml(p.version)
                                + ' · ' + escapeHtml(p.desc || '') + '</span></div>');
                        });
                        showPopover('外部插件（' + (d.plugins || []).length + '）',
                                    rows.join('') || '<div class="dp-sub">暂无外部插件</div>');
                    } else {
                        (d.skills || []).forEach(function (s) {
                            rows.push('<div class="dp-row" style="display:flex;align-items:center;gap:6px">'
                                + ICON_SVGS.zap + ' ' + escapeHtml(s)
                                + '</div>');
                        });
                        showPopover('内置技能（' + (d.skills || []).length + '）',
                                    rows.join(''));
                    }
                })
                .catch(() => showToast('清单获取失败'));
        }
        document.getElementById('dock-skills').addEventListener('click', function () { fetchPlugins('skills'); });
        document.getElementById('dock-plugins').addEventListener('click', function () { fetchPlugins('plugins'); });
        // 插件行点击（事件委托绑 popover，重渲染不丢监听；2026-10-29 二次
        // 拍板：不直发——触发词填入输入框+聚焦，用户可编辑后回车/点发送；
        // doc_ingest 无指令语义=转发 ＋ 菜单 upload 项弹文件选择）。
        popover.addEventListener('click', function (ev) {
            const row = ev.target.closest('.dp-row.dp-click');
            if (!row) return;
            const trigger = PLUGIN_QUICK_ACTIONS[row.dataset.plugin];
            closeAll();
            if (trigger === null) {
                const upItem = document.querySelector(
                    '.dock-menu-item[data-action="upload"]');
                if (upItem) upItem.click();
                return;
            }
            const inputEl = document.getElementById('chat-input');
            if (!inputEl) return;
            inputEl.value = trigger;
            inputEl.focus();
        });

        // 上下文标签条：动态渲染（摄取文档计数+转写/扫描任务态）
        function refreshContextTags() {
            const bar = document.getElementById('context-tags-bar');
            if (!bar) return;
            fetch('/api/plugins')
                .then(res => res.json())
                .then(res => {
                    const ctx = (res.data || {}).context || {};
                    const parts = [];
                    if (ctx.doc_count) {
                        // 文档标签可点开清单（2026-10-26：旧版纯 span 零绑定=
                        // 设计缺口；context-tag--link 带指针态）
                        parts.push('<span class="context-tag context-tag--link"'
                            + ' data-action="docs" title="点击查看文档清单">' + ICON_SVGS.library
                            + '已摄取文档 '
                            + ctx.doc_count + '</span>');
                    }
                    if (ctx.video_job === 'running') parts.push('<span class="context-tag"'
        + ' style="display:inline-flex;align-items:center;gap:3px">'
        + ICON_SVGS.clock + '转写中</span>');
                    if (ctx.video_last) parts.push('<span class="context-tag"'
        + ' style="display:inline-flex;align-items:center;gap:3px">'
        + ICON_SVGS.video + escapeHtml(ctx.video_last) + '</span>');
                    if (parts.length) {
                        bar.innerHTML = parts.join('');
                        bar.hidden = false;
                    } else {
                        bar.hidden = true;
                    }
                })
                .catch(() => {});
        }
        // 文档标签点击→文档清单浮层。标签条子元素每 30s 重渲染，事件委托
        // 绑静态父级（bar 本体），重渲染不丢监听。
        // 知识库文档管理器（2026-10-26 队长拍板）：清单每行=📄名（点击即
        // 重挂为附件）+大小/段数/入库时间+↻挂载+🗑删除。path 走 docsCache
        // 索引传递（路径塞 data 属性会被引号反斜杠搞坏）；行内按钮委托绑
        // popover 容器（showPopover 每次 innerHTML 重写不丢监听）。
        var docsCache = [];
        function fmtDocRow(d, i) {
            var sub = [];
            if (d.size) sub.push(escapeHtml(d.size));
            sub.push((d.chunks || 0) + ' 段');
            if (d.ingested_at) sub.push(escapeHtml(d.ingested_at));
            return '<div class="dp-row dp-doc-row">'
                + '<span class="dp-doc-main" data-act="remount" data-idx="' + i
                + '" title="点击挂载为附件，下一条消息 AI 直接读它回答" style="display:inline-flex;align-items:center;gap:4px">' + ICON_SVGS.fileText
                + escapeHtml(d.title || d.path) + '</span>'
                + '<span class="dp-sub">' + sub.join(' · ') + '</span>'
                + '<span class="dp-doc-acts">'
                + '<button class="dp-doc-btn" data-act="remount" data-idx="' + i
                + '" title="挂载为附件" style="display:inline-flex;align-items:center">'
                + ICON_SVGS.refresh + '</button>'
                + '<button class="dp-doc-btn dp-doc-del" data-act="del-doc" data-idx="' + i
                + '" title="从知识库彻底删除（切片+向量一并清除）" style="display:inline-flex;align-items:center">' + ICON_SVGS.trash + '</button>'
                + '</span></div>';
        }
        const tagsBar = document.getElementById('context-tags-bar');
        if (tagsBar) {
            tagsBar.addEventListener('click', function (ev) {
                const tag = ev.target.closest('[data-action="docs"]');
                if (!tag) return;
                fetch('/api/plugins')
                    .then(res => res.json())
                    .then(res => {
                        const ctx = (res.data || {}).context || {};
                        const docs = ctx.docs || [];
                        docsCache = docs;
                        showPopover('已摄取文档（' + (ctx.doc_count || docs.length) + '）',
                                    docs.map(fmtDocRow).join('')
                                    || '<div class="dp-sub">暂无已摄取文档</div>');
                    })
                    .catch(() => showToast('清单获取失败'));
            });
        }
        popover.addEventListener('click', function (ev) {
            const btn = ev.target.closest('[data-act]');
            if (!btn) return;
            const d = docsCache[parseInt(btn.dataset.idx, 10)];
            if (!d) return;
            if (btn.dataset.act === 'remount') {
                showToast('⏳ 正在挂载「' + (d.title || '文档') + '」…');
                fetch('/api/knowledge/doc/remount', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: d.path })
                }).then(res => res.json()).then(function (r) {
                    if (r.code === 200 && (r.data || {}).ok) {
                        showAttachBar([{ name: r.data.name,
                                         size: r.data.size || (r.data.chars + ' 字符') }]);
                        closeAll();
                        showToast('📎 已挂载「' + r.data.name + '」，直接提问即可'
                            + (r.data.source === 'chunks'
                               ? '（原文已不在，由知识切片拼回）' : ''));
                    } else {
                        showToast('❌ ' + ((r || {}).error || '挂载失败'));
                    }
                }).catch(function () { showToast('❌ 挂载失败'); });
            } else if (btn.dataset.act === 'del-doc') {
                showConfirm('删除知识库文档',
                    '确定从知识库彻底删除《' + (d.title || d.path)
                    + '》？其全部切片与向量将一并删除，不可恢复。',
                    function () {
                        fetch('/api/knowledge/doc/delete', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ path: d.path })
                        }).then(res => res.json()).then(function (r) {
                            if (r.code === 200 && (r.data || {}).ok) {
                                showToast('🗑 已删除《' + (d.title || '') + '》'
                                    + '（' + r.data.chunks + ' 块）');
                        refreshContextTags();   // 计数标签与清单即时同步
                        closeAll();
                    } else {
                        showToast('❌ ' + ((r || {}).error || '删除失败'));
                    }
                }).catch(function () { showToast('❌ 删除失败'); });
                }, { confirmText: '删除' });
            }
        });
        refreshContextTags();
        setInterval(refreshContextTags, 30000);   // 30s 低频（任务态非实时）
    })();


    // ==================== 多磁盘 ▼ 切换（UI 三期 2026-10-26） ====================
    window.__updateDiskRow = function () {
        var dsk = (window.__disks || [])[window.__diskSel || 0];
        var letter = document.getElementById('disk-letter');
        var text = document.getElementById('disk-text');
        var bar = document.getElementById('disk-bar');
        if (!dsk || !text) return;
        if (letter) letter.textContent = '(' + dsk.name + ')';
        if (text) text.textContent = dsk.used + 'GB / ' + dsk.total
            + 'GB (' + dsk.percent + '%)';
        if (bar) bar.style.width = dsk.percent + '%';
    };
    window.__renderDiskMenu = function () {
        var menu = document.getElementById('disk-menu');
        if (!menu) return;
        menu.innerHTML = (window.__disks || []).map(function (d, i) {
            return '<div class="v0-disk-item' + (i === window.__diskSel
                ? ' on' : '') + '" data-i="' + i + '">'
                + '<span>' + d.name + '</span>'
                + '<span>' + d.percent + '%</span></div>';
        }).join('');
        menu.hidden = false;
    };
    var diskTrigger = document.getElementById('disk-trigger');
    var diskMenu = document.getElementById('disk-menu');
    if (diskTrigger && diskMenu) {
        diskTrigger.addEventListener('click', function (ev) {
            ev.stopPropagation();
            if (!window.__disks || !window.__disks.length) return;
            if (diskMenu.hidden) window.__renderDiskMenu();
            else diskMenu.hidden = true;
        });
        diskMenu.addEventListener('click', function (ev) {
            var item = ev.target.closest('.v0-disk-item');
            if (!item) return;
            window.__diskSel = parseInt(item.dataset.i, 10) || 0;
            diskMenu.hidden = true;
            window.__updateDiskRow();
            ev.stopPropagation();
        });
        document.addEventListener('click', function () {
            if (diskMenu && !diskMenu.hidden) diskMenu.hidden = true;
        });   // 外点关闭（触发器/菜单项已 stopPropagation 不受影响）
    }

    // ==================== 语音输入（2026-10-25 UI 二期：🎤 两段式录音+本地转写） ====================
    // 方案：Python sounddevice 后端录音（/api/stt/start|stop 两段式）+
    // faster-whisper 本地转写（复用 video_ingest 的 _deps 底座）——比
    // MediaRecorder 稳（WebView2 getUserMedia 权限事件 pywebview 不代理）。
    // 交互：点击开始（红色波纹呼吸态）→ 再点停止 → 文字自动填入输入框
    //（不自动发送——用户可改后再发，队长口径）。
    (function initVoiceInput() {
        const mic = document.getElementById('mic-btn');
        const input = document.getElementById('chat-input');
        if (!mic || !input) return;
        let recording = false;
        // 请求在飞标志（2026-10-26 生产实锤：webview 对 start 响应处理迟滞
        // 时连点会让 recording 与后端脱同步——在飞期忽略连点+按后端应答
        // 采纳状态，双保险自愈）
        let busy = false;
        mic.addEventListener('click', function () {
            if (busy) return;
            if (!recording) {
                busy = true;
                fetch('/api/stt/start', { method: 'POST' })
                    .then(res => res.json())
                    .then(d => {
                        // 幂等语义：200 一律进录音态（含后端"已在录音中"
                        // note——前端脱同步时自此对齐后端真相）
                        if (d.code === 200) {
                            recording = true;
                            mic.classList.add('recording');
                            mic.title = '录音中…点击停止';
                            showToast((d.data && d.data.note)
                                ? '🎤 继续录音中，说完再点一次结束'
                                : '🎤 录音中，再点一次结束');
                        } else {
                            showToast('❌ ' + (d.error || '录音启动失败'));
                        }
                    })
                    .catch(() => showToast('❌ 录音服务不可达'))
                    .finally(function () { busy = false; });
            } else {
                busy = true;
                mic.classList.remove('recording');
                mic.title = '语音输入（点击开始/停止）';
                recording = false;
                showToast('⏳ 正在识别语音…');
                fetch('/api/stt/stop', { method: 'POST' })
                    .then(res => res.json())
                    .then(d => {
                        if (d.code === 200 && (d.data || {}).text) {
                            input.value = (input.value ? input.value + ' ' : '')
                                          + d.data.text;
                            input.focus();
                            showToast('✅ 已识别填入，可修改后发送');
                        } else if (d.code === 200) {
                            showToast('（没听清内容——' + ((d.data || {}).note || '空结果') + '）');
                        } else if ((d.error || '').indexOf('没有进行中的录音') >= 0) {
                            // 后端无录音（如识别完成后又点了一次）——状态已
                            // 对齐，轻提示不吓人
                            showToast('（当前没有录音了，再点麦克风开始）');
                        } else {
                            showToast('❌ ' + (d.error || '识别失败'));
                        }
                    })
                    .catch(() => showToast('❌ 识别请求失败'))
                    .finally(function () { busy = false; });
            }
        });
    })();

    // ==================== resize 视觉遮罩（白屏终极方案 B，2026-10-25） ====================
    // 窗口尺寸突变（拖拽放大/最大化）时 WebView2 GPU 重排的百毫秒级白屏/
    // 撕裂，用"视觉欺骗"遮住：resize 瞬间给 body 挂 .resizing（全屏主题灰
    // 遮罩+transition none 立即生效），150ms 防抖后移除——肉眼看到的是
    // 平滑的灰-内容过渡而非闪白。与方案 A（WS_EX_COMPOSITED 原生双缓冲）
    // 正交叠加双保险。
    (function initResizeMask() {
        let timer = null;
        window.addEventListener('resize', function () {
            document.body.classList.add('resizing');
            if (timer) clearTimeout(timer);
            timer = setTimeout(function () {
                document.body.classList.remove('resizing');
            }, 150);
        }, { passive: true });
    })();

    // ==================== UI 事件总线（#348 三期推模式） ====================
    // 页面级 EventSource 长连接（/api/events）——后台任务（插件转写等）
    // 完成时收到 video_note_done 事件，渲染为新 AI 气泡（带思考折叠+正常
    // 渲染管线）。与请求级 SSE 正交；断线自动重连（EventSource 原生）；
    // 事件丢失兜底=「查转写状态」（既有，保留）。
    (function initUiEvents() {
        if (typeof EventSource === "undefined") return;   // 老引擎降级（status 兜底）
        const es = new EventSource('/api/events');
        es.addEventListener('video_note_done', function (ev) {
            try {
                const d = JSON.parse(ev.data);
                if (d.reply) {
                    const history = document.getElementById('chat-history');
                    if (!history) return;
                    appendBotMessage(d.reply, '📺 视频转写', d.title || '');
                    history.scrollTop = history.scrollHeight;
                }
            } catch (e) {
                console.error('UI 事件渲染失败', e);   // 单事件失败不拆连接
            }
        });
        // 📊 总线进度推送：更新当前 ack 气泡内部的进度小字（不飘不插独立 div）
        es.addEventListener('bus_progress', function (ev) {
            try {
                const d = JSON.parse(ev.data);
                if (!d.text) return;
                const history = document.getElementById('chat-history');
                if (!history) return;
                // 找最后一个 bot 气泡内的进度行（有则更新/无则追加在 badge 下方）
                const bubbles = history.querySelectorAll('.message.bot-message');
                const last = bubbles[bubbles.length - 1];
                if (!last) return;
                let pl = last.querySelector('.bus-progress-line');
                if (!pl) {
                    pl = document.createElement('div');
                    pl.className = 'bus-progress-line';
                    pl.style.cssText = 'font-size:11px;color:#9ca3af;margin-top:2px;';
                    const inner = last.querySelector('.bubble-content');
                    if (inner) inner.appendChild(pl);
                }
                pl.textContent = '⏳ ' + d.text;
                history.scrollTop = history.scrollHeight;
            } catch (e) { /* 进度渲染失败不致命 */ }
        });
        // 🚌 总线异步推送（切片 a：选股等强拦截任务的结果气泡，控制台侧）
        es.addEventListener('bus_reply', function (ev) {
            try {
                const d = JSON.parse(ev.data);
                if (d.reply) {
                    const history = document.getElementById('chat-history');
                    if (!history) return;
                    // 清掉之前可能残留的进度行
                    history.querySelectorAll('.bus-progress-line').forEach(
                        function (el) { el.remove(); });
                    appendBotMessage(d.reply, d.source || '📣 总线', '');
                    history.scrollTop = history.scrollHeight;
                }
            } catch (e) {
                console.error('总线事件渲染失败', e);   // 单事件失败不拆连接
            }
        });
        es.onerror = function () { /* EventSource 原生自动重连，无需处理 */ };
        // 思考一行折叠（2026-10-28）：点击消息内思考行展开/收起全文
        document.addEventListener('click', function (ev) {
            const tl = ev.target.closest('.message.bot-message .think-live');
            if (tl) tl.classList.toggle('open');
        });
    })();

    // ==================== 天气卡真实化（#351 聚合面板一期） ====================
    // GET /api/weather（后端 15 分钟缓存）+ 前端 20 分钟轮询+载入即拉；
    // 异常/超时一律降级为"暂无数据"——绝不因网络卡顿崩面板（纪律红线）。
    // 图标后端已映射（weather_icon），前端只渲染。
    (function initWeatherCard() {
        const elTemp = document.getElementById('weather-temp');
        if (!elTemp) return;   // 节点缺失静默退出（面板降级不报错）
        const elCity = document.getElementById('weather-city');
        const elDesc = document.getElementById('weather-desc');
        const WEATHER_POLL_MS = 20 * 60 * 1000;   // 20 分钟（后端缓存 15 分钟，前端略长）
        const elMeta = document.getElementById('weather-meta');
        const elFc = document.getElementById('weather-forecast');
        function renderWeather(d) {
            if (elCity) elCity.textContent = (d.city || '天气') + ' · 今日';
            // emoji 退役（UI 三期 v0 单色 SVG 图标位）：温度只出纯数字
            if (elTemp) elTemp.textContent = Math.round(d.temp) + '°C';
            if (elDesc) elDesc.textContent = (d.desc || '') +
                (d.stale ? '（缓存·稍后自动刷新）' : '');
            // 湿度/风力胶囊（open-meteo current 真数据；缺字段整行隐藏）
            if (elMeta) {
                if (d.humidity != null || d.wind != null) {
                    elMeta.hidden = false;
                    elMeta.innerHTML =
                        '<span style="display:inline-flex;align-items:center;gap:3px">'
            + ICON_SVGS.droplet + ' ' + (d.humidity != null
                            ? Math.round(d.humidity) + '%' : '--') + '</span>'
                        + '<span style="display:inline-flex;align-items:center;gap:3px">'
            + ICON_SVGS.wind + ' ' + (d.wind != null
                            ? Math.round(d.wind) + ' km/h' : '--') + '</span>';
                } else {
                    elMeta.hidden = true;
                }
            }
            // 四天预报（今天+未来四天，open-meteo daily 真数据）
            if (elFc) {
                var fc = d.forecast || [];
                if (fc.length) {
                    elFc.hidden = false;
                    elFc.innerHTML = fc.map(function (x) {
                        return '<li><span class="v0-fc-day">' + x.day + '</span>'
                            + '<span class="v0-fc-icon">' + (x.icon || '') + '</span>'
                            + '<span class="v0-fc-temp">' + x.high + '°'
                            + '<i>/' + x.low + '°</i></span></li>';
                    }).join('');
                } else {
                    elFc.hidden = true;
                }
            }
        }
        function showUnavailable() {
            if (elTemp) elTemp.textContent = '--';
            if (elDesc) elDesc.textContent = '暂无数据（服务暂不可用）';
            if (elMeta) elMeta.hidden = true;
            if (elFc) elFc.hidden = true;
        }
        function loadWeather() {
            fetch('/api/weather')
                .then(res => res.json().then(body => ({ ok: res.ok, body: body })))
                .then(({ ok, body }) => {
                    if (ok && body.code === 200 && body.data) renderWeather(body.data);
                    else showUnavailable();
                })
                .catch(() => showUnavailable());   // 网络卡顿/断连：降级不崩
        }
        loadWeather();
        setInterval(loadWeather, WEATHER_POLL_MS);
    })();

    // 大脑来源徽标（§4.3：消费 /api/chat 返回的 source 字段）
    // dataset.prompt 记录触发本回复的原消息，供"刷新"按钮重新生成
    // 历史回放经同一入口：直出思维流块静态展示（无动画无折叠）
    function appendBotMessage(rawReply, source, prompt, opts) {
        const options = opts || {};
        const history = document.getElementById('chat-history');
        maybeTimeSeparator(options.ts || new Date().toISOString());
        const botMsg = document.createElement('div');
        botMsg.className = 'message bot-message';
        botMsg.dataset.prompt = prompt || '';
        // XSS 顺序：先在原始 reply 上切分出 <think> 块，think 与正文再各自
        // 走 textContent / renderRich 转义（不可先转义后切分）
        const thinkParts = splitThinkBlock(rawReply);
        // T4a 常驻诊断②（用户指定文案）：打印切分结果——只有 think 非 null
        // 才会进入下方卡片渲染分支；RAW_REPLY 含 <think> 而本行 PARSED_THINK
        // 为 null，即切分环节异常（此时正文会带出标签原文）
        console.log("PARSED_THINK:", thinkParts.think, "PARSED_BODY:", thinkParts.body);
        const reply = thinkParts.body;   // 剥离 think 后的正文
        const sourceBadge = source
            ? `<div class="source-badge">大脑来源：${escapeHtml(source)}</div>`
            : '';
        botMsg.innerHTML = `
            <div style="display:flex; flex-direction:column; gap:3px;">
                <div class="bubble-content">${renderRichTables(reply)}</div>
                ${sourceBadge}
                <div class="msg-tools">
                    <span class="tool-btn" onclick="copyText(this)" title="复制">
                        <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                    </span>
                    <span class="tool-btn" onclick="refreshMsg(this)" title="重新生成">
                        <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2v6h-6"></path><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path></svg>
                    </span>
                    <span class="tool-btn like-btn" onclick="toggleLike(this)" title="点赞">
                        <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"></path></svg>
                    </span>
                    <span class="tool-btn dislike-btn" onclick="toggleDislike(this)" title="踩">
                        <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"></path></svg>
                    </span>
                    <span class="tool-btn" onclick="playMsg(this)" title="播放">
                        <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path></svg>
                    </span>
                    <span class="tool-btn" onclick="forwardMsg(this)" title="转发">
                        <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"></path><polyline points="16 6 12 2 8 6"></polyline><line x1="12" y1="2" x2="12" y2="15"></line></svg>
                    </span>
                </div>
            </div>
        `;
        // 渲染入口先判 thinkMatch：仅当切分出思考内容（<think> 块或裸
        // [思考]/[计划] 段）才插思考卡片——后端全对话强制包装后，普通闲聊
        // 同样带默认占位符块，正文为自然语言或占位符都出卡；无块仍不插卡
        //（前端行为零改动），卡片位于消息气泡正文上方
        if (thinkParts.think !== null) {
            // T4a 常驻诊断③（用户指定文案）：卡片渲染分支入口——本行出现
            // 而 F12 Elements 里无 .think-live，即"执行了但插入/显示被静默
            // 吞掉"，配合下方实测校验定位
            console.log("RENDERING_THINK_LIVE...");
            // F4 加固：手工插入（不依赖 before()/prepend() 系快捷方法）——
            // 显式父引用 + insertBefore，思维流块位于气泡正文上方；插入环节
            // 任何异常都不吞掉整条回复——块插不上时再降级为深色纯文本块，
            // 思考过程必可见
            try {
                // 直出思维流收养（2026-10-22 二轮拍板）：thinkLiveEl 在位=流
                // 式块原地移动进本消息（done 已按净化全文定稿，不重建）；
                // 否则按最终口径构建静态思维流块
                const thinkLive = (options.thinkLiveEl && options.thinkLiveEl.classList &&
                                   options.thinkLiveEl.classList.contains('think-live'))
                    ? options.thinkLiveEl : buildThinkLiveBlock(thinkParts.think);
                const bubbleEl = botMsg.querySelector('.bubble-content');
                const parentEl = bubbleEl ? bubbleEl.parentNode : botMsg;
                parentEl.insertBefore(thinkLive, bubbleEl);
            } catch (e) {
                console.error("CoT Render Error: ", e);
                // 降级兜底：深色纯文本块仍插在气泡上方（消息首子节点之前）
                try {
                    botMsg.insertBefore(buildThinkFallbackBlock(thinkParts.think),
                                        botMsg.firstChild);
                } catch (fbErr) {
                    console.error("CoT Render Error: ", fbErr);
                }
            }
            // T4a 强制渲染兜底随折叠卡退役（直出块构建极简、无骨架依赖）：
            // 块插不上时上方 catch 已落深色纯文本块，思考过程必可见
        }
        history.appendChild(botMsg);
        history.scrollTop = history.scrollHeight;
        return botMsg;
    }

    // ==================== 3. 聊天历史持久化（功能文档 §12 / 界面 §10.4 近期项） ====================
    // 页面加载时拉取 /api/history 渲染历史（此前仅存页面内存、刷新即清空）
    function loadHistory() {
        fetch('/api/history')
            .then(res => res.json())
            .then(res => {
                if (res.code !== 200 || !res.data || !Array.isArray(res.data.messages)) return;
                let lastUser = '';
                let idx = 0;
                res.data.messages.forEach(m => {
                    if (!m || typeof m.content !== 'string') return;
                    // 内容错开淡入（UI 微操 2026-10-22）：仅历史回放批渲染，
                    // 流式输出的思维链/正文绝不错开（流式路径零此类）
                    let el = null;
                    if (m.role === 'user') {
                        lastUser = m.content;
                        el = appendUserMessage(m.content, m.ts);
                    } else if (m.role === 'assistant') {
                        // 历史回放共用入口：直出思维流块静态展示（无动画）
                        el = appendBotMessage(m.content, m.source || '', lastUser,
                                              { ts: m.ts });
                    }
                    if (el) {
                        el.classList.add('msg-enter');
                        el.style.animationDelay = Math.min(idx * 45, 400) + 'ms';
                    }
                    idx += 1;
                });
            })
            .catch(err => console.error('加载聊天历史失败', err));
    }
    loadHistory();

    // ==================== 4. 聊天发送逻辑 ====================
    // 等待期轮换状态：占位气泡初始"小橘3号正在思考... 🧠"，此后每 900ms
    // 依次轮换下列状态文案（数组循环），收到回复/出错即停止轮换
    const THINKING_STATUS = [
        '🧠 正在思考执行方案…',
        '👁️ 正在分析屏幕…',
        '📁 正在读取文件…',
        '⚙️ 正在执行操作…',
    ];
    const THINKING_ROTATE_MS = 900;

    // 💬 排队条（2026-10-28 对齐 ZCode）：生成中再发消息 → 缩成输入框上方
    // 一行排队条（图标=ICON_SVGS.message 矢量 + [立即执行][删除]）；立即执行=中断当前流式
    // （AbortController）转发排队消息；任务自然结束=自动补发排队消息。
    let __xj3Generating = false;
    let __xj3BusAbort = null;     // 总线任务无法 abort（后端线程）——立即执行
    let __xj3Queued = null;       // =并发二次请求（后端自排队，前端只补气泡）
    let __xj3AbortSkip = false;   // 主动中断时禁走 legacy 回退

    function ensureQueueBar() {
        let bar = document.getElementById('queue-bar');
        if (bar) return bar;
        bar = document.createElement('div');
        bar.id = 'queue-bar';
        bar.style.cssText = 'display:none;align-items:center;gap:8px;'
            + 'margin:0 12px 6px;padding:6px 12px;font-size:12px;'
            + 'background:rgba(240,243,249,0.92);border:1px solid '
            + 'var(--color-border,#e0e4ec);border-radius:8px;'
            + 'backdrop-filter:blur(4px);';
        const chatHistory = document.getElementById('chat-history');
        const inputArea = document.querySelector('.chat-input-area');
        (inputArea || chatHistory || document.body).parentNode.insertBefore(
            bar, inputArea || chatHistory);
        return bar;
    }

    function showQueueBar(text) {
        const bar = ensureQueueBar();
        bar.innerHTML = '';
        const label = document.createElement('span');
        label.innerHTML = ICON_SVGS.message
            + '<span style="margin-left:4px">排队中：' + text + '</span>';
        label.style.cssText = 'flex:1;min-width:0;overflow:hidden;'
            + 'text-overflow:ellipsis;white-space:nowrap;color:#536ba9;';
        const runBtn = document.createElement('button');
        runBtn.textContent = '立即执行';
        runBtn.style.cssText = 'font-size:11px;padding:2px 10px;border-radius:6px;'
            + 'border:1px solid var(--color-border,#e0e4ec);background:#fff;'
            + 'cursor:pointer;';
        runBtn.addEventListener('click', function () {
            const q = __xj3Queued;
            __xj3Queued = null;
            hideQueueBar();
            if (__xj3BusAbort) {   // 总线任务不可中断：并发二次请求（后端自排队）
                __xj3Generating = false;
                window.sendMessage.__force = true;
            }
            if (__xj3Abort) {      // 流式任务：中断当前再发
                __xj3AbortSkip = true;
                try { __xj3Abort.abort(); } catch (e) {}
            }
            __xj3Generating = false;
            window.sendMessage.__force = true;
            window.sendMessage();
        });
        const delBtn = document.createElement('button');
        delBtn.textContent = '删除';
        delBtn.style.cssText = 'font-size:11px;padding:2px 10px;border-radius:6px;'
            + 'border:1px solid var(--color-border,#e0e4ec);background:#fff;'
            + 'cursor:pointer;';
        delBtn.addEventListener('click', function () {
            __xj3Queued = null;
            hideQueueBar();
        });
        bar.appendChild(label);
        bar.appendChild(runBtn);
        bar.appendChild(delBtn);
        bar.style.display = 'flex';
    }

    function hideQueueBar() {
        const bar = document.getElementById('queue-bar');
        if (bar) bar.style.display = 'none';
    }

    window.__xj3GenFinish = function () {
        __xj3Generating = false;
        if (__xj3Queued) {
            const q = __xj3Queued;
            __xj3Queued = null;
            hideQueueBar();
            window.sendMessage.__force = true;
            window.sendMessage();
            void q;
        }
    };

    window.sendMessage = function() {
        const input = document.getElementById('chat-input');
        if (!input) return;

        const text = input.value.trim();
        if (!text) return;

        // 💬 排队条：生成中再发 → 缩一行排队（不直发后端）
        if (__xj3Generating && !window.sendMessage.__force) {
            __xj3Queued = text;
            showQueueBar(text);
            input.value = '';
            window.__xj3SyncSendBtn && window.__xj3SyncSendBtn();
            return;
        }
        window.sendMessage.__force = false;

        appendUserMessage(text);
        input.value = '';
        if (window.__xj3SyncSendBtn) window.__xj3SyncSendBtn();   // 清空后同步回灰（Bug①）

        const loadingMsg = document.createElement('div');
        loadingMsg.className = 'message bot-message';
        loadingMsg.style.color = '#9fb0d9';
        loadingMsg.textContent = '小橘3号正在思考... 🧠';
        const history = document.getElementById('chat-history');
        history.appendChild(loadingMsg);
        history.scrollTop = history.scrollHeight;

        // 动态轮换：每 900ms 换一条状态文案（初始文案先展示一个周期再轮换）
        let statusIdx = 0;
        const rotateTimer = setInterval(() => {
            loadingMsg.textContent = THINKING_STATUS[statusIdx % THINKING_STATUS.length];
            statusIdx += 1;
        }, THINKING_ROTATE_MS);
        __xj3Generating = true;
        __xj3AbortSkip = false;
        window.sendMessage.__force = false;

        // 🌊 思维链真流式（2026-10-05 C2，#244）：优先走 SSE 流式端点，
        // 失败/异常回退旧 /api/chat（口径零回退）。历史回放/刷新重试仍走
        // appendBotMessage 旧管线（本次只改发送链）。主动中断（排队条
        // "立即执行"）不走 legacy 回退——用户要的是插队不是重发。
        sendMessageStream(text, loadingMsg, rotateTimer)
            .catch(() => {
                if (__xj3AbortSkip) {
                    try { loadingMsg.remove(); } catch (e) {}
                    window.__xj3GenFinish && window.__xj3GenFinish();
                    return;
                }
                sendMessageLegacy(text, loadingMsg, rotateTimer);
                window.__xj3GenFinish && window.__xj3GenFinish();
            })
            .finally(() => window.__xj3GenFinish && window.__xj3GenFinish());
    };

    // 流式分支：fetch POST + getReader 手解 SSE（EventSource 不支持 POST）。
    // 2026-10-22 二轮重构：全部辅助函数提升到本函数顶层作用域——757f321 曾
    // 把 ensureThinkCard() 调用提到 fetch 前而函数本体仍声明在 .then 回调内
    // 层作用域 → 运行时 ReferenceError 同步炸掉发送链（loadingMsg 轮换孤儿
    // =界面假死；node --check 与静态锚均查不出作用域错）。本轮结构根修：
    // 调用点与声明点同层，此类雷从结构上不可能再犯。
    function sendMessageStream(text, loadingMsg, rotateTimer) {
        if (window.__xj3HideAttach) window.__xj3HideAttach();   // 附件随本次消息消费（2026-10-26）
        // C3b 修复：自取元素与作用域解耦（裸 history 解析到 window.history）
        const history = document.getElementById('chat-history');
        // ⏱️ 总闸 190s AbortController（比后端 180s 硬超时略长的最终防线）
        const ac = new AbortController();
        __xj3Abort = ac;
        const streamGuard = setTimeout(() => ac.abort(), 190000);
        // ⏱️ 看门狗（2026-10-22 救火拍板）：首帧前 30s / 帧间 90s 无任何帧
        // → 中断并就地报错（不转 legacy——同源后端会同样卡死）。任何底层
        // 卡死（工具挂死/模型无响应/流中断）UI 都不死锁，可继续发下一条。
        let watchdogFired = false;
        let watchdog = setTimeout(fireWatchdog, 30000);
        function fireWatchdog() {
            watchdogFired = true;
            try { ac.abort(); } catch (e) { /* 已中断 */ }
        }
        function patWatchdog() {   // 每帧喂狗（首帧后转为 90s 帧间口径）
            clearTimeout(watchdog);
            watchdog = setTimeout(fireWatchdog, 90000);
        }
        // ⚡ 首字零等待（2026-10-22 队长拍板）：流式状态变量提升到 fetch 之前
        // ——直出思维流骨架在点击发送的同一 tick 同步挂载，把后端 TTFT
        //（实测闲聊首帧 1.37s≈全部为模型首字延迟；指令链无模型仅 21ms）
        // 整个遮进呼吸态
        let thinkCard = null;     // 直出思维流块（发送瞬间骨架挂载，首 think 增量接管）
        let thinkBodyEl = null;   // 思考行容器
        let thinkAcc = '';        // 累计思考原文（分段剥前缀用）
        let thinkStartTs = null;  // A1（#326 前置侦察）：首个 think 增量到达时刻→耗时显示
        let answerEl = null;      // 正文气泡（首个 answer 块建）
        let answerAcc = '';
        let toolEl = null;
        let segRows = [];         // 思考行元素（按序号复用，文本变化才重写）
        let reader = null;        // SSE reader/decoder/缓冲（pump 用，then 内赋值）
        let decoder = null;
        let buf = '';
        ensureThinkCard();   // ⚡ 乐观挂载骨架（点击发送同一 tick，零等待）

        function ensureThinkCard() {
            if (thinkCard) return;
            clearInterval(rotateTimer);
            if (loadingMsg.parentNode) loadingMsg.parentNode.removeChild(loadingMsg);
            // 直出思维流（2026-10-22 二轮拍板：废弃折叠卡，对标 DeepSeek）：
            // 🧠 标签行 + 灰色小号思考行直接外冒，无箭头无折叠无二次点击
            thinkCard = document.createElement('div');
            thinkCard.className = 'think-live';
            const labelEl = document.createElement('div');
            labelEl.className = 'think-live-label';
            labelEl.textContent = '🧠 小橘正在思考…';
            thinkBodyEl = document.createElement('div');
            labelEl.addEventListener('click', function () {
                // DOM 自锚定（closest）——闭包 thinkCard 在 done 收尾被置 null，
                // 收起 1.5s 后点击读到 null 曾致 toggle 静默炸（真机无响应实锤）
                const card = labelEl.closest('.think-live');
                if (card) card.classList.toggle('think-live-collapsed');
            });
            thinkCard.appendChild(labelEl);
            thinkCard.appendChild(thinkBodyEl);
            // 骨架屏：标签呼吸 + 两根占位线，首段真文本接管时摘除
            thinkCard.classList.add('think-live-waiting');
            for (let sk = 0; sk < 2; sk++) {
                const line = document.createElement('div');
                line.className = 'think-skeleton-line' + (sk ? ' think-skeleton-short' : '');
                thinkBodyEl.appendChild(line);
            }
            history.appendChild(thinkCard);
        }

        function renderThinkProgressive() {
            ensureThinkCard();
            // 无缝接管（首字零等待配套）：首段真文本到达——摘呼吸态+清骨架线
            if (thinkCard.classList.contains('think-live-waiting')) {
                thinkCard.classList.remove('think-live-waiting');
                thinkBodyEl.querySelectorAll('.think-skeleton-line').forEach(function (el) {
                    el.remove();
                });
            }
            // 严格区分：本函数只吃 event: think（answer 走 ensureAnswerEl 通
            // 道，二者 DOM 互不沾——绝不把正文当思考，也绝不把思考当正文）
            const segs = splitThinkStageLines(thinkAcc);
            while (segRows.length < segs.length) {
                const row = document.createElement('div');
                row.className = 'think-live-line';
                thinkBodyEl.appendChild(row);
                segRows.push(row);
            }
            segs.forEach(function (seg, i) {
                if (segRows[i].textContent !== seg.text) segRows[i].textContent = seg.text;
            });
            history.scrollTop = history.scrollHeight;
        }

        // done 收口：标签换耗时（A1 口径），内容已直出、无任何折叠动画
        function finalizeThinkCard(finalThink, label) {
            thinkAcc = finalThink;
            renderThinkProgressive();
            const st = thinkCard && thinkCard.querySelector('.think-live-label');
            if (st && label) st.textContent = label;
        }

        function ensureAnswerEl() {
            if (answerEl) return;
            clearInterval(rotateTimer);
            if (loadingMsg.parentNode) loadingMsg.parentNode.removeChild(loadingMsg);
            answerEl = document.createElement('div');
            answerEl.className = 'message bot-message';
            const bubble = document.createElement('div');
            bubble.className = 'bubble-content';
            answerEl.appendChild(bubble);
            history.appendChild(answerEl);
            history.scrollTop = history.scrollHeight;
        }

        function handleEvent(etype, data) {
            patWatchdog();   // 每帧喂狗（首帧后转为 90s 帧间口径）
            if (etype === 'think') {
                if (thinkStartTs === null) {
                    thinkStartTs = Date.now();   // A1：耗时计时起点
                    const st = thinkCard && thinkCard.querySelector('.think-live-label');
                    if (st) st.textContent = '🧠 思考中…';
                }
                thinkAcc += (data.delta || '');
                renderThinkProgressive();
            } else if (etype === 'tool') {
                ensureThinkCard();   // C3b：无卡也建（工具事件不再静默丢）
                if (!toolEl) {
                    toolEl = document.createElement('div');
                    toolEl.className = 'think-live-line';
                    thinkBodyEl.appendChild(toolEl);
                }
                toolEl.textContent = '🔧 正在执行工具：' + (data.name || '');
            } else if (etype === 'answer') {
                ensureAnswerEl();
                answerAcc += (data.delta || '');
                answerEl.querySelector('.bubble-content').textContent = answerAcc;
                history.scrollTop = history.scrollHeight;
            } else if (etype === 'done') {
                // 收尾（二轮拍板直出版）：思维流块不再移除——按 done 净化全文
                // 定稿后原地移动进最终消息（正文/工具栏/落盘口径零分叉）；
                // 无流式块（指令单帧 done）走原重建路径零变化。
                // 顺序：先挂最终气泡再撤 answerEl（换屏零空白）。
                clearTimeout(streamGuard);
                clearTimeout(watchdog);
                maybeTimeSeparator(new Date().toISOString());
                let adopted = null;
                if (thinkCard) {
                    const parts = splitThinkBlock(String(data.reply == null ? '' : data.reply));
                    if (parts.think !== null && parts.think !== '') {
                        if (toolEl && toolEl.parentNode) toolEl.parentNode.removeChild(toolEl);
                        let secs = null;
                        if (thinkStartTs !== null) {
                            secs = ((Date.now() - thinkStartTs) / 1000).toFixed(1);
                        }
                        finalizeThinkCard(parts.think,
                            secs === null ? '🧠 思考过程' : '🧠 已思考（用时 ' + secs + ' 秒）');
                        adopted = thinkCard;
                        // 完成后自动收起（2026-10-25 队长验收拍板）：直出流式全程
                        // 可见，done 定稿后 1.5s 收起为折叠行（标签保留+点击可展开），
                        // 长思考不再霸屏
                        setTimeout(function () {
                            if (adopted && adopted.isConnected) {
                                adopted.classList.add('think-live-collapsed');
                            }
                        }, 1500);
                    } else {
                        // 旧口径：最终回复无 <think>（理论边角）不保留过程块
                        if (thinkCard && thinkCard.parentNode) thinkCard.parentNode.removeChild(thinkCard);
                    }
                }
                if (!adopted && toolEl && toolEl.parentNode) toolEl.parentNode.removeChild(toolEl);
                const botMsg = appendBotMessage(data.reply, data.source, text,
                    adopted ? { thinkLiveEl: adopted } : null);
                if (answerEl && answerEl.parentNode) answerEl.parentNode.removeChild(answerEl);
                thinkCard = null;
                thinkBodyEl = null;
                toolEl = null;
                answerEl = null;
                segRows = [];
                if (window.xiaoju3Sound) window.xiaoju3Sound.ding();
                if (autoTTSEnabled()) speakMessageEl(botMsg);
            } else if (etype === 'error') {
                throw new Error(data.error || 'stream error');
            }
        }

        function pump() {
            return reader.read().then(({ done, value }) => {
                if (done) return;
                buf += decoder.decode(value, { stream: true });
                let idx;
                while ((idx = buf.indexOf('\n\n')) !== -1) {
                    const frame = buf.slice(0, idx);
                    buf = buf.slice(idx + 2);
                    let etype = 'message';
                    let payload = '';
                    frame.split('\n').forEach(l => {
                        if (l.startsWith('event:')) etype = l.slice(6).trim();
                        else if (l.startsWith('data:')) payload += l.slice(5).trim();
                    });
                    if (!payload) continue;
                    handleEvent(etype, JSON.parse(payload));
                }
                return pump();
            });
        }

        return fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text }),
            signal: ac.signal
        }).then(res => {
            if (!res.ok || !res.body) throw new Error('stream unavailable');
            reader = res.body.getReader();
            decoder = new TextDecoder();
            return pump();
        }).catch(function (err) {
            clearTimeout(streamGuard);
            clearTimeout(watchdog);
            // C3b：半途断流——闭包内清理过程件再处置（外层 catch 才转 legacy
            // 重答；宽 DOM 查询会误删历史消息，必须用闭包引用）
            if (thinkCard && thinkCard.parentNode) thinkCard.parentNode.removeChild(thinkCard);
            if (toolEl && toolEl.parentNode) toolEl.parentNode.removeChild(toolEl);
            if (answerEl && answerEl.parentNode) answerEl.parentNode.removeChild(answerEl);
            if (watchdogFired) {
                // 看门狗中断：就地报错收尾，不转 legacy（同源后端会同样卡死）
                const errMsg = document.createElement('div');
                errMsg.className = 'message bot-message';
                errMsg.style.color = '#e0433f';
                errMsg.textContent = '（⏱️ 长时间无响应已自动中断——模型可能卡住，请直接重试）';
                mountSystemToolbar(errMsg);
                history.appendChild(errMsg);
                history.scrollTop = history.scrollHeight;
                return;
            }
            throw err;
        });
    }
    // 旧路分支（回退用；原实现原样保留）
    function sendMessageLegacy(text, loadingMsg, rotateTimer) {
        if (window.__xj3HideAttach) window.__xj3HideAttach();   // 附件随本次消息消费（2026-10-26）
        // C3b 修复：同 sendMessageStream——自取 history，裸名解析到
        // window.history 使 .then/.catch 全链 DOM 操作炸、回复不渲染
        const history = document.getElementById('chat-history');
        fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        })
        .then(res => res.json())
        .then(res => {
            clearInterval(rotateTimer);   // 收到回复：停止轮换并替换为正常气泡
            if (history.contains(loadingMsg)) history.removeChild(loadingMsg);   // C3b：流式回退时 loadingMsg 可能已被过程卡消费
            if (res.code === 200) {
                // T4a 常驻诊断①（用户指定文案）：打印后端原始回复全文——
                // <think> 包装块应在此可见；F12 若连本行都看不到，说明
                // 浏览器加载的是旧版 console.js（缓存或部署未更新）
                console.log("RAW_REPLY:", res.data.reply);
                const botMsg = appendBotMessage(res.data.reply, res.data.source, text);
                // 本地与远端同步：后端已将本轮问答落盘 /api/history
                // 回复到达提示音（界面文档 §6.2 / §9.1，AudioContext 缺席时静默降级）
                if (window.xiaoju3Sound) window.xiaoju3Sound.ding();
                // 任务 5：自动朗读开启时，AI 回复到达即自动播报（与手动播放同链路）
                if (autoTTSEnabled()) speakMessageEl(botMsg);
            } else {
                throw new Error(res.error || '未知错误');
            }
        })
        .catch(err => {
            clearInterval(rotateTimer);   // 出错同样停止轮换
            if (history.contains(loadingMsg)) history.removeChild(loadingMsg);
            const errMsg = document.createElement('div');
            errMsg.className = 'message bot-message';
            errMsg.style.color = '#e0433f';
            errMsg.textContent = '（请求失败：' + err.message + '）';
            mountSystemToolbar(errMsg);   // 系统提示类消息同样挂统一工具栏
            history.appendChild(errMsg);
            history.scrollTop = history.scrollHeight;
        });
    };

    // ==================== 5. 工具按钮的对应全局函数 ====================

    // 复制
    window.copyText = function(el) {
        const text = el.closest('.message').querySelector('.bubble-content').innerText;
        navigator.clipboard.writeText(text).then(() => showToast('✅ 已复制'))
            .catch(() => showToast('复制失败，请手动选择文本'));
    };

    // 刷新（§4.2 实装）：对触发该回复的原消息重新 POST /api/chat，
    // 替换当前回复气泡；后端成功后自动把重新生成的问答追加落盘（历史同步更新）
    window.refreshMsg = function(el) {
        const msgEl = el.closest('.message');
        const bubble = msgEl.querySelector('.bubble-content');
        const prompt = (msgEl && msgEl.dataset.prompt) || '';
        if (!prompt || !bubble) {
            showToast('未找到原消息，无法刷新');
            return;
        }
        const original = bubble.innerHTML;
        bubble.textContent = '正在重新生成... 🧠';
        fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: prompt })
        })
        .then(res => res.json())
        .then(res => {
            if (res.code !== 200) throw new Error(res.error || '未知错误');
            // 重新生成结果同样可能带 <think> 块或裸 [思考]/[计划] 标记：
            // 先切分（与 appendBotMessage 同口径），思考卡片同步更新，
            // 正文剥离后再渲染
            const thinkParts = splitThinkBlock(res.data.reply);
            const reply = thinkParts.body;
            syncThinkCard(msgEl, thinkParts.think);
            bubble.innerHTML = renderRich(reply);
            // 来源徽标同步更新
            let badge = msgEl.querySelector('.source-badge');
            if (res.data.source) {
                if (!badge) {
                    badge = document.createElement('div');
                    badge.className = 'source-badge';
                    bubble.after(badge);
                }
                badge.textContent = '大脑来源：' + res.data.source;
            } else if (badge) {
                badge.remove();
            }
            if (window.xiaoju3Sound) window.xiaoju3Sound.ding();
            // 任务 5：重新生成的回复同样是 AI 回复，自动朗读开启时一并播报
            if (autoTTSEnabled()) speakMessageEl(msgEl);
        })
        .catch(err => {
            bubble.innerHTML = original;   // 失败还原原回复
            showToast('刷新失败：' + err.message);
        });
    };

    // 转发（§4.2 实装）：全文复制到剪贴板，提示可粘贴转发
    window.forwardMsg = function(el) {
        const text = el.closest('.message').querySelector('.bubble-content').innerText;
        navigator.clipboard.writeText(text)
            .then(() => showToast('已复制，可粘贴转发'))
            .catch(() => showToast('复制失败，请手动选择文本'));
    };

    // 播放（朗读）——任务 5：手动点播放与自动朗读共用同一条链路入口
    // speakMessageEl（见下），本函数仅作转发。
    window.playMsg = function(el) {
        speakMessageEl(el);
    };

    // 朗读链路共用入口（手动播放 / 自动朗读同一份逻辑）——Edge-TTS 优先：
    // 解析链路（协议见 0.55）→ Edge 音色时 POST /api/tts（voice 参数带上）
    // → blob → Audio 播放；网络/4xx/5xx/超时/播放失败一律自动降级浏览器
    // speechSynthesis（清队列防连点、emoji 剔除与音色回退链零回退）。
    // emoji 剔除在入口统一做一次，两条链路共用同一份净化文本（任务 7：
    // 引擎读不出 emoji，标点保留作自然停顿）。
    function speakMessageEl(el) {
        const text = el.closest('.message').querySelector('.bubble-content').innerText;
        const speakText = stripEmojiForTTS(text);
        if (!speakText) return;
        const plan = resolveTTSMode();
        if (plan.mode !== 'edge') {
            speakWithBrowserTTS(speakText);   // 浏览器音色/未配置 Edge：原链直走
            return;
        }
        requestEdgeTTS(speakText, plan.voice)
            .then(playAudioBlob)
            .catch(() => speakWithBrowserTTS(speakText));   // 任何失败 → 自动降级
    }

    // Edge-TTS 请求：POST /api/tts {text, voice} → 200 audio/mpeg → blob。
    // AbortController 超时 8s（超时按失败降级）；非 2xx（后端 4xx/5xx JSON
    // {error}）或 200 但 Content-Type 非音频（异常网关）一律抛错走降级。
    const EDGE_TTS_TIMEOUT_MS = 8000;
    let edgeAudio = null;   // Audio 单例：连点时打断上一段，不叠音
    function requestEdgeTTS(text, voice) {
        let timer = null;
        const ctrl = (typeof AbortController === 'function') ? new AbortController() : null;
        if (ctrl) timer = setTimeout(() => ctrl.abort(), EDGE_TTS_TIMEOUT_MS);
        return fetch('/api/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text, voice: voice }),
            signal: ctrl ? ctrl.signal : undefined
        }).then(res => {
            if (!res.ok) throw new Error('TTS HTTP ' + res.status);
            return res.blob();
        }).then(blob => {
            if (blob && blob.type && blob.type.indexOf('audio') !== 0) {
                throw new Error('TTS 响应非音频：' + blob.type);
            }
            if (timer) clearTimeout(timer);
            return blob;
        }, err => {
            if (timer) clearTimeout(timer);
            throw err;
        });
    }

    // blob → Audio 播放（URL.createObjectURL；播完/出错释放，Audio 单例防叠音）
    function playAudioBlob(blob) {
        return new Promise((resolve, reject) => {
            try {
                const url = URL.createObjectURL(blob);
                if (edgeAudio) edgeAudio.pause();
                edgeAudio = new Audio();
                edgeAudio.onended = () => { URL.revokeObjectURL(url); resolve(); };
                edgeAudio.onerror = () => { URL.revokeObjectURL(url); reject(new Error('音频播放失败')); };
                edgeAudio.src = url;
                const p = edgeAudio.play();
                if (p && p.catch) {
                    p.catch(() => { URL.revokeObjectURL(url); reject(new Error('自动播放被拦截')); });
                }
            } catch (e) { reject(e); }
        });
    }

    // 浏览器 TTS 降级链（既有链路零回退）：每次播放前清空队列防连点；
    // 按回退链选择音色（localStorage → /api/status tts_voice → 中文女声 → zh
    // → 引擎默认），无可用音色时不设 utter.voice
    function speakWithBrowserTTS(text) {
        window.speechSynthesis.cancel(); // 清空之前的播放队列
        const utter = new SpeechSynthesisUtterance(text);
        utter.lang = 'zh-CN';
        const voice = pickTTSVoice();
        if (voice) utter.voice = voice;
        window.speechSynthesis.speak(utter);
    }

    // 点赞/踩：互斥逻辑（点一个自动取消另一个），再次点击可取消
    window.toggleLike = function(el) {
        const msgEl = el.closest('.message');
        const dislikeBtn = msgEl.querySelector('.dislike-btn');
        const isActive = el.classList.contains('active-like');

        el.classList.remove('active-like');
        if (dislikeBtn) dislikeBtn.classList.remove('active-dislike');

        if (!isActive) {
            el.classList.add('active-like');
            console.log('👍 已点赞');
        } else {
            console.log('已取消点赞');
        }
    };

    window.toggleDislike = function(el) {
        const msgEl = el.closest('.message');
        const likeBtn = msgEl.querySelector('.like-btn');
        const isActive = el.classList.contains('active-dislike');

        el.classList.remove('active-dislike');
        if (likeBtn) likeBtn.classList.remove('active-like');

        if (!isActive) {
            el.classList.add('active-dislike');
            console.log('👎 已踩');
        } else {
            console.log('已取消踩');
        }
    };

    // ==================== 6. 清空聊天记录（带确认语义） ====================
    const clearBtn = document.getElementById('clear-history');
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            showConfirm('清空聊天记录', '确定清空聊天记录吗？此操作不可恢复。', function () {
                fetch('/api/history', { method: 'DELETE' })
                .then(res => res.json())
                .then(res => {
                    if (res.code !== 200) throw new Error(res.error || '清空失败');
                    const history = document.getElementById('chat-history');
                    // 清空后重建欢迎语并挂统一工具栏（与首条系统欢迎语同口径）
                    history.innerHTML = '';
                    const welcome = document.createElement('div');
                    welcome.className = 'message bot-message';
                    welcome.textContent = '你好！我是小橘3号，很高兴为你服务喵~';
                    mountSystemToolbar(welcome);
                    history.appendChild(welcome);
                    showToast('聊天记录已清空');
                })
                .catch(err => showToast('清空失败：' + err.message));
            }, { confirmText: '清空' });
        });
    }

    // ==================== 7. 移动端监控抽屉开关（界面文档 §7） ====================
    const sidebar = document.querySelector('.sidebar');
    const sidebarToggle = document.getElementById('sidebar-toggle');
    if (sidebar && sidebarToggle) {
        sidebarToggle.addEventListener('click', () => sidebar.classList.toggle('open'));
    }

    // ==================== 7.2 侧栏拖拽调宽（2026-10-27） ====================
    // 把手 #sidebar-resizer（index.html flex 兄弟节点，负外边距净零位移）：
    // 指针捕获拖拽实时改 .sidebar 宽（rAF 节流不掉帧），松手持久化——桌面
    // 形态 js_api set_layout_pref 存 ui_pref.json（跨启动唯一真源，
    // localStorage 关窗即焚铁律），浏览器形态降级 localStorage。恢复以
    // ui_pref.json 为真源（api 异步就绪轮询 3s 上限，未就绪=浏览器形态
    // 静默走 localStorage）。双击复位；≤768px 抽屉态清内联宽（宽度交还
    // CSS min(80vw,300px)）；窗口缩放时已拖宽度夹紧进当前窗口。
    (function initSidebarResize() {
        const sb = document.querySelector('.sidebar');
        const handle = document.getElementById('sidebar-resizer');
        // matchMedia 缺席=非浏览器 JS 环境（node 运行时烟雾桩等），静默不启用
        if (!sb || !handle || typeof window.matchMedia !== 'function') return;
        const LS_KEY = 'xiaoju3_sidebar_width';
        const MIN_W = 300;                       // 下限同 .sidebar min-width:300px
        const mqMobile = window.matchMedia('(max-width: 768px)');
        let dragging = false, startX = 0, startW = 0, rafId = 0, pendingW = 0;

        function maxW() { return Math.max(MIN_W + 60, Math.round(window.innerWidth * 0.55)); }
        function clamp(w) { return Math.max(MIN_W, Math.min(maxW(), Math.round(w))); }
        function applyWidth(w) {
            sb.style.width = w + 'px';
            sb.style.minWidth = w + 'px';        // 压过 CSS min-width，下限由 clamp 保证
        }
        function clearWidth() {
            sb.style.removeProperty('width');
            sb.style.removeProperty('min-width');
        }
        function savedWidth() {
            let n = NaN;
            try { n = parseInt(localStorage.getItem(LS_KEY), 10); } catch (e) { /* 隐私模式 */ }
            return (n >= MIN_W && n <= 2000) ? n : 0;
        }
        function persist(w) {
            try { localStorage.setItem(LS_KEY, String(w)); } catch (e) { /* 同上 */ }
            const api = window.pywebview && window.pywebview.api;
            if (api && typeof api.set_layout_pref === 'function') {
                api.set_layout_pref(w).catch(function () {});
            }
        }
        function syncViewport() {
            if (mqMobile.matches) { clearWidth(); return; }
            const m = /^(\d+)px$/.exec(sb.style.width || '');
            if (m) applyWidth(clamp(parseInt(m[1], 10)));
        }

        handle.addEventListener('pointerdown', function (e) {
            if (mqMobile.matches || e.button !== 0) return;
            dragging = true;
            startX = e.clientX;
            startW = sb.getBoundingClientRect().width;
            handle.classList.add('dragging');
            sb.classList.add('divider-dragging');   /* 分界线拖拽态：border 保持蓝（2026-10-29） */
            document.body.style.cursor = 'col-resize';       // 拖出把手光标不闪断
            document.body.style.userSelect = 'none';         // 防拖拽选中文本
            try { handle.setPointerCapture(e.pointerId); } catch (err) { /* 旧内核无捕获 */ }
            e.preventDefault();
        });
        handle.addEventListener('pointermove', function (e) {
            if (!dragging) return;
            pendingW = clamp(startW + (e.clientX - startX));
            if (!rafId) {
                rafId = requestAnimationFrame(function () {
                    rafId = 0;
                    if (dragging) applyWidth(pendingW);
                });
            }
        });
        function endDrag() {
            if (!dragging) return;
            dragging = false;
            handle.classList.remove('dragging');
            sb.classList.remove('divider-dragging');   /* 分界线拖拽态解除 */
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            const w = clamp(sb.getBoundingClientRect().width);
            applyWidth(w);
            persist(w);
        }
        handle.addEventListener('pointerup', endDrag);
        handle.addEventListener('pointercancel', endDrag);
        handle.addEventListener('dblclick', function () {
            clearWidth();
            try { localStorage.removeItem(LS_KEY); } catch (e) { /* 同上 */ }
            const api = window.pywebview && window.pywebview.api;
            if (api && typeof api.set_layout_pref === 'function') {
                api.set_layout_pref(0).catch(function () {});   // 0=后端解释为删键复位
            }
        });
        if (mqMobile.addEventListener) mqMobile.addEventListener('change', syncViewport);
        else mqMobile.addListener(syncViewport);
        window.addEventListener('resize', function () { if (!dragging) syncViewport(); });

        restoreAndWatch();
        function restoreAndWatch() {
            const w = savedWidth();
            if (w && !mqMobile.matches) applyWidth(clamp(w));
            let tries = 0;
            const t = setInterval(function () {
                const api = window.pywebview && window.pywebview.api;
                if (api && typeof api.get_layout_pref === 'function') {
                    clearInterval(t);
                    api.get_layout_pref().then(function (r) {
                        const v = r && parseInt(r.sidebar_width, 10);
                        if (v >= MIN_W && !mqMobile.matches) applyWidth(clamp(v));
                    }).catch(function () {});
                } else if (++tries > 20) {
                    clearInterval(t);                // 浏览器形态：api 永不来，静默
                }
            }, 150);
        }
    })();

    // ==================== 7.5 终端记录标签页（对话窗口 / 终端记录切换） ====================
    // 终端记录入口（R3 后端契约承接）：标签栏切换对话窗口与终端记录两个内
    // 容区。终端记录经 GET /api/history?source=terminal 读取（后端契约：文件
    // 缺失恒 200 空列表，消息为纯 [{role, content}]），只读展示——无输入框、
    // 清空按钮禁用、消息不带操作工具栏；思考块沿用 splitThinkBlock 收敛为
    // 折叠卡片（历史回放口径：不打字、直接折叠展示全文）。切入即拉最新，
    // 停留期间每 15 秒自动刷新（降频口径：终端 CLI 每轮落盘，页面跟随，
    // 5s 轮询曾致 /api/history 后端日志量偏高），⟳ 手动刷新随时可用；
    // 竞态守卫（请求序号）丢弃慢响应，慢网不回写旧数据。
    const TERMINAL_HISTORY_URL = '/api/history?source=terminal';
    const TERMINAL_REFRESH_MS = 15000;
    // #264 B2d③ B 方案：tab 栏不再有「设置」按钮——入口=右上角⚙️齿轮/
    // 桌宠菜单「设置」，返回=设置页顶部「← 返回」（注册表 settings 条目
    // btn 恒 null，空值安全）
    const terminalPaneEl = document.getElementById('terminal-pane');
    const settingsPaneEl = document.getElementById('settings-pane');   // #264 B2a 设置页
    const settingsListEl = document.getElementById('settings-list');   // #264 B2a
    const keysEntryBtn = document.getElementById('keys-entry');        // #264 B2b 密钥管理（LV3+，探针定显隐）
    const keysPaneEl = document.getElementById('keys-pane');           // #264 B2b
    const keysListEl = document.getElementById('keys-list');           // #264 B2b
    const terminalHistoryEl = document.getElementById('terminal-history');
    const chatHistoryPaneEl = document.getElementById('chat-history');
    const chatInputAreaEl = document.querySelector('.chat-input-area');
    let terminalRefreshTimer = null;
    let terminalFetchSeq = 0;

    // 单条终端记录渲染（只读：无工具栏、无来源徽标；用户消息 textContent
    // 注入，AI 正文走 renderRich 转义——与聊天视图同口径免 XSS）
    function appendTerminalEntry(msg) {
        if (!msg || typeof msg.content !== 'string') return;
        if (msg.role === 'user') {
            const userEl = document.createElement('div');
            userEl.className = 'message user-message';
            userEl.textContent = msg.content;
            terminalHistoryEl.appendChild(userEl);
            return;
        }
        if (msg.role !== 'assistant') return;
        const parts = splitThinkBlock(msg.content);
        const botEl = document.createElement('div');
        botEl.className = 'message bot-message';
        const inner = document.createElement('div');
        inner.style.cssText = 'display:flex; flex-direction:column; gap:5px;';
        const bubble = document.createElement('div');
        bubble.className = 'bubble-content';
        bubble.innerHTML = renderRichTables(parts.body);
        inner.appendChild(bubble);
        botEl.appendChild(inner);
        if (parts.think !== null) {
            // 直出思维流块（静态不打字不动画；文本 textContent 注入免 XSS）
            botEl.insertBefore(buildThinkLiveBlock(parts.think), inner);   // 块在气泡上方（与聊天视图同构）
        }
        terminalHistoryEl.appendChild(botEl);
    }

    function loadTerminalHistory() {
        if (!terminalHistoryEl) return;
        const seq = ++terminalFetchSeq;   // 只采纳最新一次请求的响应
        fetch(TERMINAL_HISTORY_URL)
            .then(res => res.json())
            .then(res => {
                if (seq !== terminalFetchSeq) return;
                terminalHistoryEl.innerHTML = '';
                const messages = (res && res.code === 200 && res.data &&
                                  Array.isArray(res.data.messages))
                    ? res.data.messages : [];
                if (!messages.length) {
                    const empty = document.createElement('div');
                    empty.className = 'terminal-empty';
                    empty.textContent = '暂无终端记录：在终端运行 python xiaoju3.py 对话后，这里会显示终端通道的聊天记录。';
                    terminalHistoryEl.appendChild(empty);
                    return;
                }
                messages.forEach(appendTerminalEntry);
                terminalHistoryEl.scrollTop = terminalHistoryEl.scrollHeight;
            })
            .catch(err => {
                if (seq !== terminalFetchSeq) return;
                terminalHistoryEl.innerHTML = '';
                const tip = document.createElement('div');
                tip.className = 'terminal-empty';
                tip.style.color = '#e0433f';
                tip.textContent = '（终端记录读取失败：' + err.message + '）';
                terminalHistoryEl.appendChild(tip);
            });
    }

    // 标签切换（#264 B2a 重构为注册表）：新增 tab 只加 CHAT_TABS 条目，
    // 不再膨胀 if/else——pane 显隐/输入框/清空按钮/进入退出副作用全部由
    // 条目声明（B2b 密钥页、B2c 开发者暗开关直接续条目）。既有行为逐条
    // 保留：终端切入拉最新+15s 轮询、切走即停；输入框与清空按钮仅对话窗口。
    const CHAT_TABS = {
        console: {
            btn: function () { return null; },   // #UI修复：tab 栏退役，按钮已删（空值安全同 settings 条目）
            show: function () { return [chatHistoryPaneEl]; },
            // 2026-10-29 穿透修复：hide 必须收全四个视图——旧清单漏
            // keysPaneEl，密钥页点「← 返回」后 keys 面板留在聊天下方穿模
            //（队长截图实锤；terminal.hide 同漏同修）
            hide: function () { return [terminalPaneEl, settingsPaneEl, keysPaneEl]; },
            input: true,
            clearTitle: '清空聊天记录',
            enter: null,
            leave: null,
        },
        terminal: {
            btn: function () { return null; },   // #UI修复：tab 栏退役，按钮已删
            show: function () { return [terminalPaneEl]; },
            hide: function () { return [chatHistoryPaneEl, settingsPaneEl, keysPaneEl]; },   // 2026-10-29 穿透修复：补 keysPaneEl（同 console 条目）
            input: false,
            clearTitle: '',
            enter: function () {
                loadTerminalHistory();   // 每次切入拉最新
                if (!terminalRefreshTimer) {
                    terminalRefreshTimer = setInterval(loadTerminalHistory, TERMINAL_REFRESH_MS);
                }
            },
            leave: function () {
                if (terminalRefreshTimer) {
                    clearInterval(terminalRefreshTimer);   // 切走即停，不留后台轮询
                    terminalRefreshTimer = null;
                }
            },
        },
        settings: {
            btn: function () { return null; },   // #264 B2d③：tab 栏无设置按钮（B 方案），空值安全
            show: function () { return [settingsPaneEl]; },
            hide: function () { return [chatHistoryPaneEl, terminalPaneEl, keysPaneEl]; },
            input: false,
            clearTitle: '',
            enter: function () {
                document.body.classList.add('xiaoju3-settings-open');   // 桌宠随设置族隐藏（批 4 收尾补丁）
                loadSettings();   // 链式调 loadPersonaCard（人格卡随设置拉取）
            },
            leave: function () {
                document.body.classList.remove('xiaoju3-settings-open');
            },
        },
        keys: {
            btn: function () { return keysEntryBtn; },   // #264 B2b：LV3+ 才显示（探针定显隐）
            show: function () { return [keysPaneEl]; },
            hide: function () { return [chatHistoryPaneEl, terminalPaneEl, settingsPaneEl]; },
            input: false,
            clearTitle: '',
            enter: function () {
                document.body.classList.add('xiaoju3-settings-open');   // 密钥页同族同藏
                loadKeys();   // 切入即拉掩码
            },
            leave: function () {
                document.body.classList.remove('xiaoju3-settings-open');
            },
        },
    };
    let activeChatTab = 'console';

    function switchChatTab(tab) {
        const def = CHAT_TABS[tab];
        if (!def) return;
        Object.keys(CHAT_TABS).forEach(function (name) {
            const d = CHAT_TABS[name];
            if (d.btn()) d.btn().classList.toggle('active', name === tab);
        });
        def.show().forEach(function (el) { if (el) el.hidden = false; });
        def.hide().forEach(function (el) { if (el) el.hidden = true; });
        if (chatInputAreaEl) chatInputAreaEl.hidden = !def.input;
        // #264 B2d③ 回归修复：输入框显隐改变桌宠下界基准（隐藏=窗口底/
        // 可见=输入框上沿），pane 切完立即按新基准重钳——设置/终端落过底
        // 的桌宠切回对话窗不再卡进输入框/发送按钮区
        if (window.__xiaoju3Pet && typeof window.__xiaoju3Pet.reclamp === 'function') {
            window.__xiaoju3Pet.reclamp();
        }
        const clearBtnEl = document.getElementById('clear-history');
        if (clearBtnEl) {
            clearBtnEl.disabled = !def.clearTitle;
            clearBtnEl.title = def.clearTitle || '该页无此操作';
        }
        if (activeChatTab !== tab) {
            const prev = CHAT_TABS[activeChatTab];
            if (prev && prev.leave) prev.leave();
            activeChatTab = tab;
        }
        if (def.enter) def.enter();
    }

    // #UI修复（2026-10-13）：顶部 tab 栏取消——终端/设置经 🧰 面板进入；
    // tabConsoleBtn/tabTerminalBtn 常量与绑定随之退役（settings 先例：
    // btn 恒 null 空值安全，此处直接删——不留引用已删 DOM 的死代码）
    // #264 B2d③ 回归修复：旧 tab-settings 按钮绑定块随 B 方案删除——
    // const 已移除但此块曾残留，对已删变量的事实引用在运行时抛
    // ReferenceError 打断 IIFE 求值，其后所有绑定（⚙️齿轮/桥/关于/返回）
    // 全部失效（node --check 抓不到：语法合法、运行时才炸）。设置入口现只
    // 经齿轮/桌宠菜单。
    const terminalRefreshBtn = document.getElementById('terminal-refresh');
    const terminalBackBtn = document.getElementById('terminal-back');
    if (terminalBackBtn) {
        terminalBackBtn.addEventListener('click', function () {
            switchChatTab('console');   // #UI修复：tab 取消后的终端页返回回路
        });
    }
    if (terminalRefreshBtn) {
        terminalRefreshBtn.addEventListener('click', loadTerminalHistory);
    }
    const settingsSaveBtn = document.getElementById('settings-save');
    if (settingsSaveBtn) settingsSaveBtn.addEventListener('click', saveSettings);
    const settingsRefreshBtn = document.getElementById('settings-refresh');
    if (settingsRefreshBtn) settingsRefreshBtn.addEventListener('click', loadSettings);
    // #264 B2d③ B 方案：设置页「← 返回」= 回对话窗口（tab 栏无设置按钮后的退出路径）
    const settingsBackBtn = document.getElementById('settings-back');
    if (settingsBackBtn) settingsBackBtn.addEventListener('click', function () { switchChatTab('console'); });
    // #264 B2b 密钥管理绑定：入口按钮（探针放行后才可见）+返回+刷新
    if (keysEntryBtn) {
        keysEntryBtn.addEventListener('click', function () { switchChatTab('keys'); });
    }
    const keysBackBtn = document.getElementById('keys-back');
    if (keysBackBtn) keysBackBtn.addEventListener('click', function () { switchChatTab('console'); });
    const keysRefreshBtn = document.getElementById('keys-refresh');
    if (keysRefreshBtn) keysRefreshBtn.addEventListener('click', loadKeys);
    probeKeysAccess();   // 页面加载即定 🔑 显隐（LV3+ 门）

    // ==================== 7.6 设置页（#264 B2a，B1 API 契约） ====================
    // 数据=GET /api/settings → {code,level,items:[{key,label,tier,type,value}]}：
    // 低档项后端已按 level 隐藏——前端只渲染返回 items，零键名硬编码；
    // 保存=POST {updates}（只提交改动项）；403 → toast 权限不足（含所需
    // 等级/TOTP 原因）；响应 applied=已写 .env 并补 os.environ（🟢 即改
    // 即生效），其余 written=需重启。类型渲染：str/int/bool/enum(:a,b,c)。
    let settingsFetchSeq = 0;
    let personaFetchSeq = 0;   // 人格卡独立竞态守卫（与 settings 互不挤兑）
    const SETTINGS_STATE = { level: null, original: {}, tiers: {} };
    const SETTINGS_TIER_LABELS = {
        daily: '常规设置',
        admin: '管理员开关',
        danger: '高危险（保存需 Lv.4+TOTP）',
    };

    function settingsChecked(value) {
        return String(value) === '1' || String(value) === 'true';
    }

    function appendSettingsTip(text) {
        const tip = document.createElement('div');
        tip.className = 'settings-empty';
        tip.textContent = text;
        settingsListEl.appendChild(tip);
    }

    function buildSettingsField(it) {
        SETTINGS_STATE.original[it.key] = it.value;
        SETTINGS_STATE.tiers[it.key] = it.tier || 'other';   // #264 B2c b：TOTP 分流需要
        const row = document.createElement('label');
        row.className = 'first-run-field settings-field';
        const cap = document.createElement('span');
        cap.textContent = (it.label || it.key) + '（' + it.key + '）';
        row.appendChild(cap);
        const type = String(it.type || '');
        let input;
        if (type === 'bool') {
            input = document.createElement('input');
            input.type = 'checkbox';
            input.checked = settingsChecked(it.value);
        } else if (type.indexOf('enum:') === 0) {
            input = document.createElement('select');
            const cur = String(it.value === null || it.value === undefined ? '' : it.value);
            const options = String(type.slice(5)).split(',').filter(function (o) { return o; });
            if (cur && options.indexOf(cur) === -1) options.push(cur);   // 表外现值原样保留，防保存误改
            options.forEach(function (opt) {
                const o = document.createElement('option');
                o.value = opt;
                o.textContent = opt;
                input.appendChild(o);
            });
            input.value = cur || (options[0] || '');
            if (!cur) SETTINGS_STATE.original[it.key] = input.value;   // 空现值记默认选中，防幻影 diff
        } else {
            input = document.createElement('input');
            input.type = (type === 'int') ? 'number' : 'text';
            input.value = it.value === null || it.value === undefined ? '' : String(it.value);
        }
        input.className = 'settings-input';
        input.id = 'settings-field-' + it.key;
        input.dataset.key = it.key;
        input.dataset.type = type || 'str';
        input.autocomplete = 'off';
        row.appendChild(input);
        return row;
    }

    // 界面偏好（#264 B2d④ 静态本地组）：与 API items 并列渲染，不走分档
    // 表——主题色=前端偏好（THEME_KEY），退出方式=js_api 读写 ui_pref.json。
    // 浏览器形态（无 pywebview）下退出方式禁用置灰。


    function appendUiPrefsSection() {
        if (!settingsListEl) return;
        const title = document.createElement('div');
        title.className = 'settings-group-title';
        title.textContent = '界面偏好（本机）';
        settingsListEl.appendChild(title);
        // 主题色
        const themeField = document.createElement('label');
        themeField.className = 'first-run-field settings-field';
        const themeCap = document.createElement('span');
        themeCap.textContent = '主题色';
        themeField.appendChild(themeCap);
        const themeSel = document.createElement('select');
        themeSel.className = 'settings-input';
        themeSel.id = 'ui-pref-theme';
        [['', '深蓝（默认）'], ['orange', '暖橘 🦊']].forEach(function (pair) {
            const o = document.createElement('option');
            o.value = pair[0];
            o.textContent = pair[1];
            themeSel.appendChild(o);
        });
        themeSel.value = getStoredTheme() || '';
        themeSel.addEventListener('change', function () {
            applyTheme(themeSel.value);   // 复用既有主题设施（data-theme 切换）
            try {
                if (themeSel.value) localStorage.setItem(THEME_KEY, themeSel.value);
                else localStorage.removeItem(THEME_KEY);
            } catch (e) { /* localStorage 不可用时仅本次会话生效 */ }
            showToast('主题已切换');
        });
        themeField.appendChild(themeSel);
        settingsListEl.appendChild(themeField);
        // 退出方式
        const exitField = document.createElement('label');
        exitField.className = 'first-run-field settings-field';
        const exitCap = document.createElement('span');
        exitCap.textContent = '退出方式（勾过「记住」后生效；改回「每次询问」恢复弹窗）';
        exitField.appendChild(exitCap);
        const exitSel = document.createElement('select');
        exitSel.className = 'settings-input';
        exitSel.id = 'ui-pref-exit';
        [['ask', '每次询问'], ['backend_only', '直接退窗口（后端与 NapCat 保留）'],
         ['full_exit', '直接完全退出（含 NapCat）']].forEach(function (pair) {
            const o = document.createElement('option');
            o.value = pair[0];
            o.textContent = pair[1];
            exitSel.appendChild(o);
        });
        exitField.appendChild(exitSel);
        settingsListEl.appendChild(exitField);
        const api = window.pywebview && window.pywebview.api;
        if (!api || typeof api.get_exit_pref !== 'function') {
            exitSel.disabled = true;
            exitSel.title = '浏览器形态不可用（桌面窗口内生效）';
            return;
        }
        api.get_exit_pref().then(function (pref) {
            exitSel.value = pref || 'ask';
        }).catch(function () { exitSel.disabled = true; });
        exitSel.addEventListener('change', function () {
            window.pywebview.api.set_exit_pref(exitSel.value).then(function (r) {
                showToast(r && r.ok ? '✅ 退出方式已保存' : '⚠️ 保存失败');
            }).catch(function (err) { showToast('保存失败: ' + err.message); });
        });
    }

    function renderSettingsItems(data) {
        if (!settingsListEl) return;
        SETTINGS_STATE.level = data && data.level;
        const items = (data && Array.isArray(data.items)) ? data.items : [];
        SETTINGS_STATE.original = {};
        // #264 B2c 修正：关于条目已移进滚动容器（settings-list 内部），
        // innerHTML 清空前先摘出来，重渲染后放回列表尾
        const aboutRow = document.getElementById('settings-about');
        if (aboutRow && aboutRow.parentElement === settingsListEl) {
            aboutRow.remove();
        }
        // 人格卡（批 4）同款保护：不清空即被抹，重渲染后放回（关于之前）
        const personaCard = document.getElementById('persona-card');
        if (personaCard && personaCard.parentElement === settingsListEl) {
            personaCard.remove();
        }
        settingsListEl.innerHTML = '';
        appendUiPrefsSection();   // #264 B2d④ 静态本地组（与 API 组并列，始终渲染）
        if (!items.length) {
            appendSettingsTip('暂无可见设置项（当前等级或分档表限制）');
            applyDevSwitchRow();   // 开关行恢复（空列表路径）
            if (personaCard) settingsListEl.appendChild(personaCard);
            if (aboutRow) settingsListEl.appendChild(aboutRow);
            return;
        }
        const groups = [];
        const byTier = {};
        items.forEach(function (it) {
            const tier = it.tier || 'other';
            if (!byTier[tier]) { byTier[tier] = []; groups.push(tier); }
            byTier[tier].push(it);
        });
        // #264 B2c 收尾（用户拍板）：admin 组藏进开发者模式——
        // dev_mode_on=false 时跳过渲染（藏/显是 UI 门；能不能改仍由后端
        // level 管=双门，此处只影响可见性）
        const devOn = DEV_STATE.mode_on === true;
        groups.forEach(function (tier) {
            if (tier === 'admin' && !devOn) return;   // 藏：拨开发者模式 ON 才出现
            const title = document.createElement('div');
            title.className = 'settings-group-title';
            title.textContent = SETTINGS_TIER_LABELS[tier] || tier;
            if (tier === 'danger') {
                title.style.color = 'var(--color-danger, #e0433f)';   // #264 B2c c：高危组红色标识
            }
            settingsListEl.appendChild(title);
            byTier[tier].forEach(function (it) {
                settingsListEl.appendChild(buildSettingsField(it));
            });
        });
        if (personaCard) settingsListEl.appendChild(personaCard);   // 人格卡放回（关于之前）
        if (aboutRow) settingsListEl.appendChild(aboutRow);   // 关于放回列表尾
        applyDevSwitchRow();   // #264 B2c：开关行按 ui_pref 恢复（渲染尾）（滚动内容一部分）
    }

    function loadSettings() {
        if (!settingsListEl) return;
        const seq = ++settingsFetchSeq;   // 竞态守卫（与终端页同口径）：慢响应丢弃
        fetch('/api/settings')
            .then(function (res) { return res.json(); })
            .then(function (body) {
                if (seq !== settingsFetchSeq) return;
                if (!body || body.code !== 200) {
                    const aboutRow = document.getElementById('settings-about');
                    if (aboutRow) aboutRow.remove();
                    settingsListEl.innerHTML = '';
                    appendUiPrefsSection();   // 静态组不依赖 API 成败
                    applyDevSwitchRow();   // 开关行恢复（失败路径）
                    if (aboutRow) settingsListEl.appendChild(aboutRow);
                    appendSettingsTip('设置读取失败' +
                        (body && body.error ? ('：' + body.error) : ''));
                    return;
                }
                renderSettingsItems(body);
            })
            .catch(function (err) {
                if (seq !== settingsFetchSeq) return;
                const aboutRow = document.getElementById('settings-about');
                if (aboutRow) aboutRow.remove();
                settingsListEl.innerHTML = '';
                appendUiPrefsSection();   // 静态组不依赖 API 成败
                applyDevSwitchRow();   // 开关行恢复（catch 路径）
                if (aboutRow) settingsListEl.appendChild(aboutRow);
                appendSettingsTip('设置读取失败: ' + err.message);
            });
        loadPersonaCard();   // 人格卡（#271 批 4）：独立容器，与 settings-list 成败互不牵连
    }

    // ==================== 人格卡（#271 批 4，2026-10-15） ====================
    // 纯状态展示批铁律：只展示+手动锁+开关，零触发层改动；文案=行为层
    // 描述（用户化翻译，禁止标签化/临床表述）；权限预检=state 自带 level，
    // 低于 3 → 置灰 + 提示，不渲染任何可点击 UI。
    const PERSONA_MODE_PHRASES = {
        banter: '爱跟你拌嘴，像老朋友损你',
        familiar: '自来熟，说话不绕弯',
        caring: '爱操心，嘘寒问暖',
        dependent: '爱粘着你，有事没事找你聊',
        polite: '客客气气，保持一点距离'
    };
    const PERSONA_MODE_LABELS = {
        banter: '斗嘴型', familiar: '熟络型', caring: '照顾型',
        dependent: '依赖型', polite: '客气型'
    };
    const PERSONA_SWITCH_UI = {
        banter: { label: '爱拌嘴', on: '一定要拌嘴', off: '别拌嘴' },
        clingy: { label: '偶尔撒娇', on: '撒娇管够', off: '不撒娇' },
        tsundere: { label: '嘴硬心软', on: '傲娇上线', off: '直来直去' },
        quiet_companion: { label: '安静陪着', on: '多陪少说', off: '该说说' },
        proactive_care: { label: '主动问冷暖', on: '会主动问', off: '先别主动' },
        proactive_banter: { label: '主动找你斗嘴', on: '会来找茬', off: '安分点' }
    };
    const PERSONA_AUTO_TEXT = '跟着感觉走';

    function personaSourceText(state) {
        if (state.manual) return '这是你亲手定的';
        if (state.source === 'auto') {
            const pct = Math.round((state.confidence || 0) * 100);
            return '这是它自己判断的' + (pct > 0 ? ('（把握 ' + pct + '%）') : '');
        }
        return '还没摸熟，先客客气气相处';
    }

    function loadPersonaCard() {
        const box = document.getElementById('persona-card');
        if (!box) return;
        const seq = ++personaFetchSeq;   // 独立竞态守卫（共用会挤掉 settings 渲染）
        fetch('/api/persona/state')
            .then(function (res) { return res.json(); })
            .then(function (body) {
                if (seq !== personaFetchSeq) return;
                renderPersonaCard(box, body || {});
            })
            .catch(function () {
                if (seq !== personaFetchSeq) return;
                box.hidden = false;
                box.classList.add('persona-locked');
                box.textContent = '人格状态读取失败，稍后再试。';
            });
    }

    function renderPersonaCard(box, body) {
        box.hidden = false;
        box.innerHTML = '';
        const hasLevel = body.level !== undefined;
        const level = Number(body.level || 0);
        if (hasLevel && level < 3) {
            // 权限预检（D13=Lv3）：未达标置灰+提示，不渲染可点击 UI
            box.classList.add('persona-locked');
            const tip = document.createElement('div');
            tip.className = 'persona-sub';
            tip.textContent = '人格设置需要 Lv.3' +
                (level > 0 ? ('（当前 Lv.' + level + '）') : '') +
                '——提升等级后可以查看和调整小橘的相处状态。';
            box.appendChild(tip);
            return;
        }
        box.classList.remove('persona-locked');
        const state = body.state || {};
        const title = document.createElement('div');
        title.className = 'persona-title';
        title.textContent = '人格';
        box.appendChild(title);

        const main = document.createElement('div');
        main.className = 'persona-mode-main';
        main.textContent = PERSONA_MODE_PHRASES[state.mode] ||
            '还在摸脾气的阶段';
        box.appendChild(main);

        const sub = document.createElement('div');
        sub.className = 'persona-sub';
        const label = PERSONA_MODE_LABELS[state.mode] || '';
        sub.textContent = personaSourceText(state) +
            (label ? ('（' + label + '）') : '');
        box.appendChild(sub);

        const lockRow = document.createElement('div');
        lockRow.className = 'persona-modes';
        Object.keys(PERSONA_MODE_PHRASES).forEach(function (mode) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = PERSONA_MODE_PHRASES[mode];
            if (state.mode === mode && state.manual) btn.classList.add('active');
            btn.addEventListener('click', function () {
                postPersona('manual_mode', { mode: mode });
            });
            lockRow.appendChild(btn);
        });
        const autoBtn = document.createElement('button');
        autoBtn.className = 'persona-auto-btn';
        autoBtn.textContent = '恢复自动判断';
        if (!state.manual) autoBtn.classList.add('active');
        autoBtn.addEventListener('click', function () {
            postPersona('manual_mode', { clear: true });
        });
        lockRow.appendChild(autoBtn);
        box.appendChild(lockRow);

        const switches = document.createElement('div');
        switches.className = 'persona-switches';
        Object.keys(PERSONA_SWITCH_UI).forEach(function (name) {
            const ui = PERSONA_SWITCH_UI[name];
            const cur = (state.switches && state.switches[name]) || {};
            const value = cur.value || 'auto';
            const row = document.createElement('div');
            row.className = 'persona-switch-row';
            const labelEl = document.createElement('span');
            labelEl.textContent = ui.label;
            row.appendChild(labelEl);
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = value === 'auto' ? PERSONA_AUTO_TEXT
                : (value === 'on' ? ui.on : ui.off);
            btn.addEventListener('click', function () {
                const next = value === 'auto' ? 'on'
                    : (value === 'on' ? 'off' : 'auto');
                postPersona('switch', { name: name, value: next });
            });
            row.appendChild(btn);
            switches.appendChild(row);
        });
        box.appendChild(switches);

        const meta = document.createElement('div');
        meta.className = 'persona-sub';
        meta.textContent = '你们已经聊了 ' + (state.interactions || 0) +
            ' 次。' + (state.expression_ready
                ? '个性语气已上线。'
                : '还在熟悉中（聊满 50 次后个性语气上线，当前 ' +
                  (state.interactions || 0) + ' 次）。');
        box.appendChild(meta);
    }

    function postPersona(action, payload) {
        const box = document.getElementById('persona-card');
        if (!box) return;
        fetch('/api/persona/' + action, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }).then(function (res) { return res.json(); })
          .then(function (body) {
              // 错误路径一律 toast + 卡片原样保留（批 4 验收 Bug 2：
              // POST 响应无 level 曾把整卡抹成置灰提示）
              if (body && body.code === 403) {
                  showToast('⚠️ 权限不足（需要 Lv.3）');
                  return;
              }
              if (!body || body.code !== 200 || !body.state) {
                  showToast('⚠️ 保存失败，稍后再试');
                  return;
              }
              renderPersonaCard(box, {
                  level: body.level,          // 后端回传（同 GET 口径）
                  state: body.state
              });
          })
          .catch(function () { showToast('⚠️ 保存失败，稍后再试'); });
    }

    function collectSettingsUpdates() {
        const updates = {};
        if (!settingsListEl) return updates;
        settingsListEl.querySelectorAll('.settings-input').forEach(function (input) {
            const key = input.dataset.key;
            if (!key) return;
            const orig = SETTINGS_STATE.original[key];
            if (input.dataset.type === 'bool') {
                if (input.checked !== settingsChecked(orig)) {
                    updates[key] = input.checked ? '1' : '0';
                }
            } else if (String(orig === null || orig === undefined ? '' : orig) !== input.value) {
                updates[key] = input.value;
            }
        });
        return updates;
    }

    function settingsDenyText(body) {
        if (body && body.error === 'level_insufficient') {
            return '权限不足（需要 Lv.' + (body.required || '?') + '）';
        }
        if (body && body.error === 'childlock_off_requires_lv4_totp') {
            return '关闭儿童锁需要 Lv.4 + TOTP 验证';
        }
        if (body && body.error === 'totp_required') return '需要 TOTP 验证';
        if (body && body.error === 'totp_invalid') return 'TOTP 验证码无效';
        return '权限不足';
    }

    function saveSettings() {
        const updates = collectSettingsUpdates();
        const keys = Object.keys(updates);
        if (!keys.length) { showToast('没有修改项'); return; }
        // #264 B2c b：改动含 danger 档 → 先 TOTP 验证（前端卡片）再提交
        const dangerKeys = keys.filter(function (k) {
            return SETTINGS_STATE.tiers[k] === 'danger';
        });
        if (dangerKeys.length) {
            openTotpDialog(updates, dangerKeys);
            return;
        }
        submitSettingsUpdates(updates, null);
    }

    // 危险项后果文案（按项区分，设计稿 §三 4：高危保存弹确认含后果）
    const DANGER_CONSEQUENCES = {
        LOCAL_MODEL: '改主模型会影响所有对话的模型调用',
        CLOUD_MODEL: '改云模型会影响云端脑对话',
        XIAOJU3_PERSONALITY: '改人格档会影响说话风格与自称',
        HA_URL: '改 HA 地址会影响全屋智能联动',
        ONEBOT_API_URL: '改 OneBot 地址会影响 QQ 通道收发',
        VISION_API_URL: '改视觉地址会影响看图能力',
        WORKSPACE: '改工作区路径会影响文件读写位置（重启生效）',
    };

    function submitSettingsUpdates(updates, totp) {
        const payload = { updates: updates };
        if (totp) payload.totp = totp;
        fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
            .then(function (res) {
                return res.json().then(function (body) {
                    return { status: res.status, body: body };
                });
            })
            .then(function (r) {
                const body = r.body || {};
                if (r.status === 403 || body.code === 403) {
                    if (body.error === 'totp_invalid') {
                        showToast('⚠️ TOTP 验证码错误，请重试');
                        openTotpDialog(updates, Object.keys(updates).filter(function (k) {
                            return SETTINGS_STATE.tiers[k] === 'danger';
                        }), totp);   // 带上次的码便于改一位重试
                        return;
                    }
                    showToast('⚠️ ' + settingsDenyText(body));
                    return;
                }
                if (r.status !== 200 && body.code !== 200) {
                    showToast('保存失败' + (body.error ? ('：' + body.error) : ''));
                    return;
                }
                const written = Array.isArray(body.written) ? body.written : [];
                const applied = Array.isArray(body.applied) ? body.applied : [];
                const restart = written.filter(function (k) {
                    return applied.indexOf(k) === -1;
                });
                let msg = '✅ 已保存 ' + written.length + ' 项';
                if (applied.length) msg += '，' + applied.length + ' 项已生效';
                if (restart.length) msg += '，' + restart.length + ' 项重启后生效';
                showToast(msg);
                loadSettings();   // 保存后重拉：值与可见性以后端为真相
            })
            .catch(function (err) { showToast('保存失败: ' + err.message); });
    }

    // ==================== 高危 TOTP 验证卡（#264 B2c b） ====================
    // danger 项保存前置验证：6 位码+按项后果文案；403 totp_invalid →
    // 带旧码重开卡便于改一位重试；成功走 submitSettingsUpdates 常规链。
    let totpDialogEl = null;

    function closeTotpDialog() {
        if (totpDialogEl) {
            totpDialogEl.remove();
            totpDialogEl = null;
        }
    }

    function openTotpDialog(updates, dangerKeys, prefill) {
        closeTotpDialog();
        const overlay = document.createElement('div');
        overlay.id = 'totp-overlay';
        overlay.style.cssText = 'position:fixed;inset:0;z-index:2147483000;'
            + 'background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;';
        const card = document.createElement('div');
        card.style.cssText = 'background:var(--color-card,#fff);color:var(--color-text,#222);'
            + 'border:1px solid var(--color-danger,#e0433f);border-radius:10px;padding:20px 24px;'
            + 'width:min(420px,92vw);box-shadow:0 8px 30px rgba(0,0,0,.35);font-size:14px;';
        const title = document.createElement('div');
        title.textContent = '🛠️ 高危操作验证';
        title.style.cssText = 'font-size:16px;font-weight:700;color:var(--color-danger,#e0433f);margin-bottom:10px;';
        card.appendChild(title);
        dangerKeys.forEach(function (k) {
            const line = document.createElement('div');
            line.style.cssText = 'margin:4px 0;';
            line.textContent = '⚠️ ' + k + '：' + (DANGER_CONSEQUENCES[k] || '即将修改该项配置');
            card.appendChild(line);
        });
        const hint = document.createElement('div');
        hint.textContent = '请输入 6 位动态码（TOTP）确认操作：';
        hint.style.cssText = 'margin:12px 0 6px;';
        card.appendChild(hint);
        const input = document.createElement('input');
        input.type = 'text';
        input.inputMode = 'numeric';
        input.maxLength = 6;
        input.value = prefill || '';
        input.autocomplete = 'off';
        input.style.cssText = 'width:100%;box-sizing:border-box;padding:8px;border:1px solid rgba(127,127,127,.4);'
            + 'border-radius:6px;font-family:Consolas,monospace;font-size:18px;letter-spacing:.4em;text-align:center;';
        card.appendChild(input);
        const errTip = document.createElement('div');
        errTip.className = 'first-run-error';
        errTip.hidden = true;
        card.appendChild(errTip);
        const btnRow = document.createElement('div');
        btnRow.style.cssText = 'display:flex;gap:10px;justify-content:flex-end;margin-top:12px;';
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'header-btn';
        cancelBtn.textContent = '取消';
        cancelBtn.addEventListener('click', closeTotpDialog);
        const okBtn = document.createElement('button');
        okBtn.className = 'header-btn';
        okBtn.textContent = '确认执行';
        okBtn.addEventListener('click', function () {
            const code = input.value.trim();
            if (!/^\d{6}$/.test(code)) {
                errTip.textContent = '请输入 6 位数字动态码';
                errTip.hidden = false;
                return;
            }
            closeTotpDialog();
            submitSettingsUpdates(updates, code);
        });
        btnRow.appendChild(cancelBtn);
        btnRow.appendChild(okBtn);
        card.appendChild(btnRow);
        overlay.appendChild(card);
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) closeTotpDialog();
        });
        document.body.appendChild(overlay);
        totpDialogEl = overlay;
        input.focus();
    }

    // ==================== 开发者模式暗入口（#264 B2c，持久化拍板） ====================
    // 状态=ui_pref.json 两字段（dev_unlocked/dev_mode_on，后端文件——
    // localStorage 关窗即焚禁用）；解锁永久、开关永久，F5/重启读文件恢复，
    // 无任何重置路径（用户拍板推翻设计稿原「会话级」口径）。连点=解锁仪式
    // （已解锁则提示开关在下方）；开关行拨 ON/OFF 独立持久化+审计；
    // LV3+ 每次触发写一条审计（js_api dev_audit → settings_log）。
    let devTapCount = 0;
    let devTapTimer = null;

    const DEV_STATE = { unlocked: false, mode_on: false };   // #264 B2c 收尾：内存镜像（真源=ui_pref.json）

    function applyDevBadges(on) {
        // 🛠️ 徽标统一挂/摘（「关于」条目标题+关于卡内版本号）
        const aboutLabel = document.querySelector('#settings-about .settings-about-label');
        if (aboutLabel) {
            const has = aboutLabel.textContent.indexOf('🛠️') !== -1;
            if (on && !has) aboutLabel.textContent += ' 🛠️';
            if (!on && has) aboutLabel.textContent = aboutLabel.textContent.replace(' 🛠️', '');
        }
        const cardVer = document.querySelector('#about-overlay .about-version');
        if (cardVer) {
            const has = cardVer.textContent.indexOf('🛠️') !== -1;
            if (on && !has) cardVer.textContent += ' 🛠️';
            if (!on && has) cardVer.textContent = cardVer.textContent.replace(' 🛠️', '');
        }
        // footer 版本号：解锁态橙字+浅橙底块（F5/重启恢复）
        const fv = document.getElementById('footer-version');
        if (fv) {
            fv.style.color = on ? 'var(--color-primary, #d96f2b)' : '';
            fv.style.background = on ? 'rgba(217, 111, 43, 0.15)' : '';
            fv.style.padding = on ? '1px 8px' : '';
            fv.style.borderRadius = on ? '6px' : '';
            fv.style.fontWeight = on ? '700' : '';
        }
    }

    function setDevMode(on, reason) {
        // 开发者模式开/关（持久化拍板）：写 ui_pref.json + 徽标 + 审计
        const api = window.pywebview && window.pywebview.api;
        if (!api || typeof api.set_dev_pref !== 'function') return;
        api.set_dev_pref(null, on).then(function (r) {
            if (!(r && r.ok)) return;
            DEV_STATE.mode_on = on;
            applyDevBadges(on);
            applyDevSwitchRow();
            showToast((on ? '🛠️ 开发者模式已开启' : '开发者模式已关闭')
                + (reason ? ('（' + reason + '）') : ''));
            if (api.dev_audit) api.dev_audit('dev_mode ' + (on ? 'enter' : 'exit') + ' ' + (reason || ''));
        }).catch(function () { showToast('保存失败'); });
    }

    function handleDevTap() {
        devTapCount += 1;
        clearTimeout(devTapTimer);
        devTapTimer = setTimeout(function () { devTapCount = 0; }, 3000);
        if (devTapCount < 7) return;
        devTapCount = 0;
        const level = SETTINGS_STATE.level;
        const api = window.pywebview && window.pywebview.api;
        if (level === null || level === undefined) {
            showToast('⚠️ 权限未知（请先打开设置页读取）');
            return;
        }
        if (level < 3) {
            showToast('⚠️ 权限不足（Lv.' + level + '）');
            return;
        }
        if (!api || typeof api.get_dev_pref !== 'function') {
            showToast('桌面窗口未就绪（浏览器形态不可用）');
            return;
        }
        api.get_dev_pref().then(function (pref) {
            if (pref && pref.unlocked) {
                // 已解锁：不重复仪式，指路开关行
                showToast('开发者模式开关已在下方（设置页底部）');
                if (api.dev_audit) api.dev_audit('tap7 already-unlocked level=' + level);
                return;
            }
            // 首次解锁：unlocked+mode_on 同写 true + 徽标 + 开关行 + 审计
            api.set_dev_pref(true, true).then(function (r) {
                if (!(r && r.ok)) { showToast('解锁失败'); return; }
                DEV_STATE.unlocked = true;
                DEV_STATE.mode_on = true;
                applyDevBadges(true);
                applyDevSwitchRow();
                markFooterVersionUnlocked();
                showToast('🔓 开发者模式已解锁（设置页底部展开「开发者模式」）');
                if (api.dev_audit) api.dev_audit('dev_mode enter tap7 level=' + level);
            }).catch(function () { showToast('解锁失败'); });
            }).catch(function () { showToast('桌面窗口未就绪'); });
    }
    // 解锁瞬间视觉反馈：footer 版本号变橙（#UI修复 2026-10-13）
    function markFooterVersionUnlocked() {
        const fv = document.getElementById('footer-version');
        if (fv) {
            // D 拍板：浅橙背景块（一眼可见）；C 图标砍掉
            fv.style.background = 'rgba(217, 111, 43, 0.15)';
            fv.style.color = 'var(--color-primary, #d96f2b)';
            fv.style.padding = '1px 8px';
            fv.style.borderRadius = '6px';
            fv.style.fontWeight = '700';
        }
    }

    // 连点绑定（#264 B2c 收尾）：关于卡内版本号（藏得更深=暗入口语义）；
    // 事件委托挂 body——卡是动态节点，开卡后即可连点
    document.body.addEventListener('click', function (e) {
        if (e.target && e.target.classList &&
            e.target.classList.contains('about-version')) {
            handleDevTap();
        }
        // #UI修复 2026-10-13：第二触发点=页面底部版本号（更显眼的自然位）
        if (e.target && e.target.id === 'footer-version') {
            handleDevTap();
        }
    });
    // ==================== 开发者模式开关行（#264 B2c 持久化） ====================
    // 位置=设置页「关于」条目上方；dev_unlocked=true 才显示；拨 ON/OFF 独立
    // 持久化（dev_mode_on）+徽标+审计；F5/重启按文件恢复（无重置路径）。
    function buildDevSwitchRow() {
        // 折叠式交互（2026-10-13 拍板）：标题行「开发者模式」+原生 details
        // 折叠（默认收起；将来开发者选项都收纳进此 details）
        const row = document.createElement('details');
        row.className = 'settings-about-row';
        row.id = 'dev-switch-row';
        const sum = document.createElement('summary');
        sum.style.cssText = 'cursor:pointer;font-weight:700;font-size:13px;'
            + 'list-style:revert;';
        sum.textContent = '开发者模式';
        row.appendChild(sum);
        const body = document.createElement('div');
        body.style.cssText = 'padding:6px 0 2px;';
        const sw = document.createElement('label');
        sw.style.cssText = 'display:flex;align-items:center;gap:6px;cursor:pointer;';
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.id = 'dev-mode-switch';
        input.addEventListener('change', function () {
            setDevMode(input.checked, 'switch');
        });
        sw.appendChild(input);
        const txt = document.createElement('span');
        txt.style.cssText = 'font-size:12px;opacity:.7;';
        txt.textContent = '高危项 TOTP 验证+审计';
        sw.appendChild(txt);
        body.appendChild(sw);
        row.appendChild(body);
        return row;
    }

    function applyDevSwitchRow() {
        const api = window.pywebview && window.pywebview.api;
        const list = document.getElementById('settings-list');
        if (!api || typeof api.get_dev_pref !== 'function' || !list) return;
        api.get_dev_pref().then(function (pref) {
            DEV_STATE.unlocked = !!(pref && pref.unlocked);
            DEV_STATE.mode_on = !!(pref && pref.mode_on);
            let row = document.getElementById('dev-switch-row');
            if (!(pref && pref.unlocked)) {
                if (row) row.remove();   // 未解锁：开关行不显示
                applyDevBadges(false);
                return;
            }
            const on = !!(pref && pref.mode_on);
            if (!row) {
                row = buildDevSwitchRow();
                const about = document.getElementById('settings-about');
                if (about) list.insertBefore(row, about);   // 关于条目上方
                else list.appendChild(row);
            }
            const input = row.querySelector('#dev-mode-switch');
            if (input) input.checked = on;
            applyDevBadges(on);   // F5/重启恢复徽标
        }).catch(function () {});
    }

    // 「关于」条目 click → openAbout（复用 B2d 桌宠菜单同卡）
    const aboutRow = document.getElementById('settings-about');
    if (aboutRow) aboutRow.addEventListener('click', function () { openAbout(); });

    // ==================== 8. 缩成加速球（2026-10-03 口径：⌄ 缩桌宠成球） ====================
    // 与桌宠（desktop-pet.js）的协作：本节只切换 body 的 xiaoju3-pet-minimized
    // 类与球体显隐/定位，不注入/不修改桌宠任何节点（桌宠隐藏由 CSS 类驱动）。
    // 球体为 index.html 静态节点 #xiaoju3-ball（60px 圆形、橘色 Q 版边框、
    // 小橘头像）；控制台主体（.sidebar + .chat-area）永不隐藏（口径①）。
    // 球跟桌宠走（口径②）：进入最小化时从 __xiaoju3Pet.getPos() 实时取桌宠
    // 坐标重放球位（球心对齐桌宠心），位置不由球记忆（无 localStorage 持久化）；
    // 互切幂等（重复最小化/恢复不报错、不抖动），球体挂载点缺失时全部静默
    // 跳过，无 JS 报错路径。（PET_BALL_FIX_DESIGN）
    const PET_MINIMIZE_CLASS = 'xiaoju3-pet-minimized';
    const BALL_SIZE = 60;   // 球体直径（px，与 index.html #xiaoju3-ball 一致）

    function getBallEl() {
        return document.getElementById('xiaoju3-ball');
    }

    // 球体位置钳制在视口内（拖拽中与 resize 重钳制共用）
    function clampBallPos(x, y) {
        const maxW = Math.max(0, document.documentElement.clientWidth - BALL_SIZE);
        const maxH = Math.max(0, document.documentElement.clientHeight - BALL_SIZE);
        return {
            x: Math.min(Math.max(x, 0), maxW),
            y: Math.min(Math.max(y, 0), maxH),
        };
    }

    function applyBallPos(pos) {
        const ball = getBallEl();
        if (!ball) return;
        const c = clampBallPos(pos.x, pos.y);
        ball.style.left = c.x + 'px';
        ball.style.top = c.y + 'px';
        ball.style.right = 'auto';
        ball.style.bottom = 'auto';
    }

    // （位置持久化已退役：口径②球跟桌宠走，位置不由球记忆——每次进入
    // 最小化都按 __xiaoju3Pet.getPos() 实时原位重放，拖拽仅会话内生效）

    // 球跟桌宠（PET_BALL_FIX_DESIGN §2/§3）：从桌宠单例实时取坐标重放球位
    // （球心对齐桌宠心）；桌宠单例缺失/坐标异常时保持现状（回退 CSS 兜底位）
    function replayBallAtPet() {
        const pos = (window.__xiaoju3Pet && typeof window.__xiaoju3Pet.getPos === 'function')
            ? window.__xiaoju3Pet.getPos() : null;
        if (!pos || typeof pos.x !== 'number' || typeof pos.y !== 'number') return;
        const w = (typeof pos.w === 'number' && pos.w > 0) ? pos.w : BALL_SIZE;
        const h = (typeof pos.h === 'number' && pos.h > 0) ? pos.h : BALL_SIZE;
        applyBallPos({
            x: pos.x + (w - BALL_SIZE) / 2,
            y: pos.y + (h - BALL_SIZE) / 2,
        });
    }

    // 桌宠最小化/恢复互切（幂等）：已是目标状态直接返回，不重复操作。
    // 最小化 = 桌宠缩成球（CSS 类驱动桌宠隐藏 + 球显示），控制台永不缩
    function setPetMinimized(minimized) {
        const ball = getBallEl();
        if (!ball) return;   // 球体挂载点缺失：静默跳过，无 JS 报错路径
        const isMin = document.body.classList.contains(PET_MINIMIZE_CLASS);
        if (isMin === minimized) return;
        if (minimized) replayBallAtPet();   // 先重放球位（桌宠尚可见，尺寸取真实值）
        document.body.classList.toggle(PET_MINIMIZE_CLASS, minimized);
    }

    // 球体交互初始化：点击展开、指针拖拽移动（拖拽阈值口径与桌宠一致：
    // 位移平方>9），松手超阈值存位置、未拖动视为点击展开；防重复绑定（幂等）
    function initConsoleBall() {
        const ball = getBallEl();
        if (!ball || ball.dataset.ballBound === '1') return;
        ball.dataset.ballBound = '1';
        let dragging = false;
        let moved = false;
        let startX = 0, startY = 0, offX = 0, offY = 0;
        ball.addEventListener('pointerdown', function (e) {
            dragging = true;
            moved = false;
            startX = e.clientX;
            startY = e.clientY;
            const rect = ball.getBoundingClientRect();
            offX = e.clientX - rect.left;
            offY = e.clientY - rect.top;
            try { ball.setPointerCapture(e.pointerId); } catch (err) { /* 老引擎忽略 */ }
        });
        ball.addEventListener('pointermove', function (e) {
            if (!dragging) return;
            const dx = e.clientX - startX;
            const dy = e.clientY - startY;
            if (dx * dx + dy * dy > 9) moved = true;   // 拖拽阈值（位移平方>9）
            if (moved) applyBallPos({ x: e.clientX - offX, y: e.clientY - offY });
        });
        ball.addEventListener('pointerup', function () {
            if (!dragging) return;
            dragging = false;
            if (!moved) {
                setPetMinimized(false);   // 未拖动＝点击恢复桌宠
            }
            // 拖动＝会话内自由摆位（applyBallPos 已实时落位）；不持久化，
            // 下次进入最小化按桌宠实时原位重放
        });
        // 拖拽被系统打断（来电/手势竞争）：复位拖拽态，不误判为点击
        ball.addEventListener('pointercancel', function () { dragging = false; });
        // 窗口尺寸变化：最小化态下按桌宠当前原位重放球位并钳制在视口内
        window.addEventListener('resize', function () {
            if (document.body.classList.contains(PET_MINIMIZE_CLASS)) {
                replayBallAtPet();
            }
        });
    }

    // #264 B2d ②：⌄ 原为「桌宠缩球」入口，现改齿轮=设置 tab（缩球功能
    // 迁入桌宠右键菜单「缩小」项，经 __xiaoju3Console.setPetMinimized 调用）；
    // 菜单批次的桥与 setPetMinimized 全保留，本处只换入口语义
    const settingsEntryBtn = document.getElementById('console-settings-entry');
    if (settingsEntryBtn) {
        settingsEntryBtn.addEventListener('click', function () {
            switchChatTab('settings');
        });
    }
    initConsoleBall();

    // 球体头像裂图兜底：素材缺失（404）时退化为 🦊 emoji 圆球——不改显隐
    // 类控制（display 仍由 CSS 类管），最小化态永不出现空球/裂图图标
    (function bindBallImgFallback() {
        const ball = getBallEl();
        const img = (ball && ball.querySelector) ? ball.querySelector('img') : null;
        if (!img) return;
        img.addEventListener('error', function () {
            img.remove();
            ball.textContent = '🦊';
            ball.style.textAlign = 'center';
            ball.style.lineHeight = '52px';   // 60px 球体减去上下 3px 橘色描边
            ball.style.fontSize = '30px';
        });
    })();

    // ==================== 首装引导覆盖层（安装器方案步 A4b/C） ====================
    // 跳过语义（方案 C）：后端文件承载（xiaoju3_data/.first_run_skipped），
    // 彻底弃用 localStorage——浏览器/WebView2 容器差异免疫。
    function setFirstRunError(msg) {
        const el = document.getElementById('first-run-error');
        if (!el) return;
        if (msg) { el.textContent = msg; el.hidden = false; }
        else { el.textContent = ''; el.hidden = true; }
    }

    function closeFirstRunOverlay() {
        const overlay = document.getElementById('first-run-overlay');
        if (overlay) overlay.hidden = true;
    }

    function initFirstRun() {
        // 弹与不弹由后端 status 判定（.env 与跳过标记两个文件，容器无关）
        fetch('/api/first_run/status')
            .then(res => res.json())
            .then(res => {
                if (!(res.code === 200 && res.data && res.data.first_run)) return;
                // 安装器意向报告并行独立拉取（步 B3 消费端）：自带 catch 独立降级，
                // 不合并等待——报告慢/缺失绝不拖累探针弹出
                fetch('/api/first_run/installer_report')
                    .then(r3 => r3.json())
                    .then(r3 => { renderInstallerReport(r3 && r3.data); })
                    .catch(() => { /* 报告缺失降级：hints 块保持隐藏 */ });
                return fetch('/api/first_run/probes')
                    .then(r2 => r2.json())
                    .then(r2 => { showFirstRun(r2.data && r2.data.probes); });
            })
            .catch(() => { /* 引导层静默降级：控制台照常使用 */ });
    }

    function showFirstRun(probes) {
        const list = document.getElementById('first-run-probes');
        if (list) {
            list.innerHTML = '';
            (probes || []).forEach(function (p) {
                const li = document.createElement('li');
                li.textContent = (p.ok ? '🟢' : '🟡') + ' ' + p.name + '：' + (p.detail || '');
                list.appendChild(li);
            });
        }
        const urlInput = document.getElementById('first-run-local-url');
        if (urlInput && !urlInput.value) {
            urlInput.value = 'http://127.0.0.1:11434/api/chat';
        }
        const overlay = document.getElementById('first-run-overlay');
        if (overlay) overlay.hidden = false;
    }

    function renderInstallerReport(data) {
        // 安装器意向报告只读展示（步 B3 消费端）：铁律=不预填表单、不写 .env、
        // 不预勾自启、不因意向跳过任何探针、不碰 DEVICE_TIER（真档位归
        // hardware_profiler 复测）。内容一律 textContent，绝不拼 HTML。
        const box = document.getElementById('first-run-install-hints');
        if (!box) return;
        box.innerHTML = '';
        box.hidden = true;
        const d = (data && typeof data === 'object') ? data : {};
        if (!d.available) return;
        const intents = (d.intents && typeof d.intents === 'object') ? d.intents : {};
        const labels = { ollama: '本地 Ollama', napcat: 'QQ(NapCat)', ha: 'HA 心跳' };
        const picked = Object.keys(labels).filter(function (k) {
            return intents[k] === true;
        });
        const metaBits = [];
        if (d.installed_at) metaBits.push('安装于 ' + d.installed_at);
        if (d.tier_hint) metaBits.push('安装器建议：' + d.tier_hint + '（真实档位以本机复测为准）');
        if (!picked.length && !metaBits.length) return;   // available 但三项全无：保持隐藏
        if (picked.length) {
            const badge = document.createElement('div');
            badge.textContent = '安装时勾选：' + picked.map(function (k) {
                return labels[k];
            }).join(' / ');
            box.appendChild(badge);
        }
        if (metaBits.length) {
            const meta = document.createElement('div');
            meta.textContent = metaBits.join('；');
            box.appendChild(meta);
        }
        box.hidden = false;
    }

    function submitFirstRun(skip) {
        if (skip) {
            // 跳过：后端写跳过标记文件（.env 不写），first_run 自然翻转为 false
            fetch('/api/first_run/skip', { method: 'POST' })
                .then(res => res.json())
                .then(res => {
                    if (res.code === 200) {
                        closeFirstRunOverlay();
                        if (typeof showToast === 'function') {
                            showToast('已跳过首装引导，可稍后编辑 xiaoju3_data\\.env');
                        }
                    } else {
                        setFirstRunError(res.error || '跳过失败，请重试');
                    }
                })
                .catch(() => setFirstRunError('网络异常，请重试'));
            return;
        }
        const keyInput = document.getElementById('first-run-deepseek-key');
        const key = ((keyInput && keyInput.value) || '').trim();
        if (key && !(key.indexOf('sk-') === 0 && key.length >= 30)) {
            // 本地格式校验拦截：不发请求
            setFirstRunError('DeepSeek key 格式不对（应以 sk- 开头且足够长），未提交');
            return;
        }
        setFirstRunError('');
        const val = function (id) {
            const el = document.getElementById(id);
            return (el && el.value) ? el.value.trim() : '';
        };
        const payload = {
            env: {
                DEEPSEEK_API_KEY: key,
                HA_URL: val('first-run-ha-url'),
                HA_TOKEN: val('first-run-ha-token'),
                LOCAL_URL: val('first-run-local-url'),
                USER_CITY: val('first-run-user-city'),
            },
            autostart: !!(document.getElementById('first-run-autostart') &&
                          document.getElementById('first-run-autostart').checked),
        };
        fetch('/api/first_run/complete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
        .then(res => res.json())
        .then(res => {
            if (res.code === 200) {
                closeFirstRunOverlay();
                if (typeof showToast === 'function') {
                    showToast('配置已保存，关闭窗口重新打开即生效');
                }
                setFirstRunError('');
                const hint = document.getElementById('first-run-restart-hint');
                if (hint) hint.hidden = false;
                const closeBtn = document.getElementById('first-run-restart-btn');
                if (closeBtn) closeBtn.hidden = false;   // 点击 → window.close() 触发整树终止，重开读新配置
            } else {
                setFirstRunError(res.error || '保存失败，请重试');
            }
        })
        .catch(function () {
            setFirstRunError('网络异常，配置未保存，请重试');
        });
    }

    const frSkipBtn = document.getElementById('first-run-skip');
    if (frSkipBtn) frSkipBtn.addEventListener('click', function () { submitFirstRun(true); });
    const frDoneBtn = document.getElementById('first-run-done');
    if (frDoneBtn) frDoneBtn.addEventListener('click', function () { submitFirstRun(false); });
    const frRestartBtn = document.getElementById('first-run-restart-btn');
    if (frRestartBtn) frRestartBtn.addEventListener('click', function () { window.close(); });
    const frDsLinkBtn = document.getElementById('first-run-ds-link');
    if (frDsLinkBtn) frDsLinkBtn.addEventListener('click', function () {
        // DeepSeek 开放平台（外链按 UI 哨兵口径不放 index.html 字面量，由 JS 打开新窗口）
        try { window.open('https://platform.deepseek.com', '_blank', 'noopener'); } catch (err) { /* 弹窗被拦时忽略 */ }
    });

    // 单点插入（IIFE 尾部）：所有既有绑定完成后再尝试弹引导
    initFirstRun();

    // ==================== 关于卡 + 退出 stub + 桥（#264 B2d 第①批） ====================
    // 关于卡=极简拍板（名称+版本+一句话+Apache 2.0）；退出=stub 占位（双方法
    // 确认弹窗+js_api 全退链随第③批界面偏好组落地，设计稿第五节）；桥=桌宠
    // 右键菜单跨 IIFE 调用入口（镜像 __xiaoju3Pet 反向桥模式，方法缺失时
    // desktop-pet.js 侧 console.warn 兜底）。
    function openAbout() {
        const exist = document.getElementById('about-overlay');
        if (exist) { exist.hidden = false; return; }
        const overlay = document.createElement('div');
        overlay.id = 'about-overlay';
        overlay.style.cssText = 'position:fixed;inset:0;z-index:2147483000;'
            + 'background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;';
        const card = document.createElement('div');
        card.style.cssText = 'background:var(--color-card,#fff);color:var(--color-text,#222);'
            + 'border:1px solid var(--color-primary,#d96f2b);border-radius:10px;padding:22px 26px;'
            + 'width:min(340px,92vw);box-shadow:0 8px 30px rgba(0,0,0,.35);text-align:center;font-size:14px;';
        const logo = document.createElement('div');
        logo.textContent = '🦊 小橘3号';
        logo.style.cssText = 'font-size:20px;font-weight:700;margin-bottom:6px;';
        const verText = window.__xiaoju3Version || '';
        const ver = document.createElement('div');
        ver.className = 'about-version';   // 连点 7 次=开发者暗入口（B2c 收尾）
        ver.textContent = verText ? ('v' + verText) : 'v1.0.4';
        ver.title = '连点 7 次查看权限状态';
        ver.style.cssText = 'opacity:.75;margin-bottom:10px;cursor:default;user-select:none;';
        const desc = document.createElement('div');
        desc.textContent = '长期主线的本地优先智能体——桌宠+控制台+QQ 三通道。';
        desc.style.cssText = 'margin-bottom:10px;';
        const lic = document.createElement('div');
        lic.textContent = '开源许可：Apache License 2.0';
        lic.style.cssText = 'font-size:12px;opacity:.65;margin-bottom:14px;';
        const closeBtn = document.createElement('button');
        closeBtn.className = 'header-btn';
        closeBtn.textContent = '关闭';
        closeBtn.addEventListener('click', function () { overlay.hidden = true; });
        card.appendChild(logo);
        card.appendChild(ver);
        card.appendChild(desc);
        card.appendChild(lic);
        card.appendChild(closeBtn);
        overlay.appendChild(card);
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) overlay.hidden = true;
        });
        document.body.appendChild(overlay);
    }

    function quitApp() {
        // #264 B2d④：真实现——与主窗 X 统一弹窗（双方法 radio+记住选择，
        // Python closing 拦截经 evaluate_js 调同一弹窗； remembering 走
        // js_api 存 ui_pref.json——localStorage 关窗即焚禁用）
        __xiaoju3OpenQuitDialog();
    }

    // ==================== 退出弹窗（#264 B2d④） ====================
    // 双方法 radio（只退窗口/完全退出）+「记住我的选择」（经 js_api 存
    // agent_state/ui_pref.json）；桌宠菜单 quitApp 与主窗 X（Python
    // closing 拦截 evaluate_js）统一走 __xiaoju3OpenQuitDialog。已记住
    // 时（pref≠ask）两端都不弹、直接按记住的方法退出。
    let quitDialogEl = null;

    function closeQuitDialog() {
        if (quitDialogEl) {
            quitDialogEl.remove();
            quitDialogEl = null;
        }
    }

    function showQuitDialog() {
        if (quitDialogEl) { quitDialogEl.hidden = false; return; }
        const overlay = document.createElement('div');
        overlay.id = 'quit-overlay';
        overlay.style.cssText = 'position:fixed;inset:0;z-index:2147483000;'
            + 'background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;';
        const card = document.createElement('div');
        card.style.cssText = 'background:var(--color-card,#fff);color:var(--color-text,#222);'
            + 'border:1px solid var(--color-primary,#d96f2b);border-radius:10px;padding:20px 24px;'
            + 'width:min(400px,92vw);box-shadow:0 8px 30px rgba(0,0,0,.35);font-size:14px;';
        const title = document.createElement('div');
        title.textContent = '是否退出小橘3号？';
        title.style.cssText = 'font-size:16px;font-weight:700;margin-bottom:10px;';
        card.appendChild(title);
        let selected = 'backend_only';
        [['backend_only', '只退窗口（后端与 NapCat 继续运行）'],
         ['full_exit', '完全退出（前端+后端+NapCat 全部关闭）']].forEach(function (r, i) {
            const lab = document.createElement('label');
            lab.style.cssText = 'display:block;margin:8px 0;cursor:pointer;';
            const input = document.createElement('input');
            input.type = 'radio';
            input.name = 'quit-mode';
            input.value = r[0];
            input.checked = i === 0;
            input.addEventListener('change', function () { selected = r[0]; });
            lab.appendChild(input);
            lab.appendChild(document.createTextNode(' ' + r[1]));
            card.appendChild(lab);
        });
        const rememberLab = document.createElement('label');
        rememberLab.style.cssText = 'display:block;margin:10px 0;font-size:12px;opacity:.8;cursor:pointer;';
        const remember = document.createElement('input');
        remember.type = 'checkbox';
        rememberLab.appendChild(remember);
        rememberLab.appendChild(document.createTextNode(' 记住我的选择，下次不再询问'));
        card.appendChild(rememberLab);
        const btnRow = document.createElement('div');
        btnRow.style.cssText = 'display:flex;gap:10px;justify-content:flex-end;margin-top:12px;';
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'header-btn';
        cancelBtn.textContent = '取消';
        cancelBtn.addEventListener('click', closeQuitDialog);
        const okBtn = document.createElement('button');
        okBtn.className = 'header-btn';
        okBtn.textContent = '确认退出';
        okBtn.addEventListener('click', function () {
            const api = window.pywebview && window.pywebview.api;
            if (!api || typeof api.quit_app !== 'function') {
                showToast('桌面窗口未就绪（浏览器形态请在窗口上退出）');
                return;
            }
            api.quit_app(selected, remember.checked);
            closeQuitDialog();
            showToast(remember.checked ? '已记住退出方式，正在退出…' : '正在退出…');
        });
        btnRow.appendChild(cancelBtn);
        btnRow.appendChild(okBtn);
        card.appendChild(btnRow);
        overlay.appendChild(card);
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) closeQuitDialog();
        });
        document.body.appendChild(overlay);
        quitDialogEl = overlay;
    }

    function __xiaoju3OpenQuitDialog() {
        const api = window.pywebview && window.pywebview.api;
        if (api && typeof api.get_exit_pref === 'function') {
            api.get_exit_pref().then(function (pref) {
                if (pref === 'backend_only' || pref === 'full_exit') {
                    api.quit_app(pref);   // 记住过：两端都不弹，按记住的方法直接走
                    return;
                }
                showQuitDialog();
            }).catch(function () { showQuitDialog(); });
            return;
        }
        showToast('桌面窗口未就绪（浏览器形态请在窗口上退出）');
    }
    window.__xiaoju3OpenQuitDialog = __xiaoju3OpenQuitDialog;   // Python closing 拦截入口

    // ==================== 密钥管理（#264 B2b，方案 A） ====================
    // 数据=GET /api/keys → {code,level,items:[{key,masked,set}]}：掩码由
    // 后端拼好（前3+****+后4），**前端零明文接触**（渲染只用 masked/set，
    // 铁律=设计稿第五节）；覆盖=POST {key,value,confirm:true}（二次确认
    // window.confirm——设计稿拍板防误操作）；LV3+ 门=页面加载探针
    // （403→🔑 hidden，后端 403 双保险）。
    let keysFetchSeq = 0;

    function appendKeysTip(text) {
        const tip = document.createElement('div');
        tip.className = 'settings-empty';
        tip.textContent = text;
        keysListEl.appendChild(tip);
    }

    function buildKeysRow(it) {
        const row = document.createElement('div');
        row.className = 'first-run-field settings-field keys-field';
        const cap = document.createElement('span');
        cap.textContent = it.key;
        row.appendChild(cap);
        const maskRow = document.createElement('div');
        maskRow.className = 'keys-row';
        const masked = document.createElement('span');
        masked.className = 'keys-masked';
        masked.textContent = it.set ? (it.masked || '****') : '未配置';
        masked.style.cssText = it.set ? '' : 'opacity:.55;';
        maskRow.appendChild(masked);
        const editBtn = document.createElement('button');
        editBtn.className = 'header-btn';
        editBtn.textContent = '改';
        editBtn.title = '覆盖 ' + it.key;
        editBtn.addEventListener('click', function () { startKeyEdit(row, it); });
        maskRow.appendChild(editBtn);
        row.appendChild(maskRow);
        return row;
    }

    function renderKeysItems(data) {
        if (!keysListEl) return;
        const items = (data && Array.isArray(data.items)) ? data.items : [];
        keysListEl.innerHTML = '';
        if (!items.length) {
            appendKeysTip('暂无可见密钥项');
            return;
        }
        items.forEach(function (it) { keysListEl.appendChild(buildKeysRow(it)); });
    }

    function startKeyEdit(row, it) {
        const existing = row.querySelector('.keys-edit');
        if (existing) { existing.querySelector('input').focus(); return; }
        const edit = document.createElement('div');
        edit.className = 'keys-edit';
        edit.style.cssText = 'margin-top:6px;';
        const input = document.createElement('input');
        input.type = 'password';
        input.autocomplete = 'off';
        input.placeholder = '粘贴新值（只写不读，保存后仅显示掩码）';
        input.style.cssText = 'width:100%;box-sizing:border-box;padding:6px 8px;'
            + 'border:1px solid rgba(127,127,127,.4);border-radius:6px;';
        const btns = document.createElement('div');
        btns.style.cssText = 'display:flex;gap:8px;margin-top:6px;justify-content:flex-end;';
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'header-btn';
        cancelBtn.textContent = '取消';
        cancelBtn.addEventListener('click', function () { edit.remove(); });
        const saveBtn = document.createElement('button');
        saveBtn.className = 'header-btn';
        saveBtn.textContent = '保存';
        saveBtn.addEventListener('click', function () {
            const value = input.value;
            if (!value.trim()) { showToast('新值不能为空'); return; }
            // 二次确认（设计稿第五节拍板：防误操作，旧值不可恢复）——现代弹窗
            showConfirm('覆盖密钥', '确认覆盖 ' + it.key + ' 吗？旧值不可恢复。', function () {
                fetch('/api/keys', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key: it.key, value: value, confirm: true })
                })
                .then(function (res) {
                    return res.json().then(function (body) {
                        return { status: res.status, body: body };
                    });
                })
                .then(function (r) {
                    const body = r.body || {};
                    if (r.status === 403 || body.code === 403) {
                        showToast('⚠️ 权限不足（需要 Lv.3）');
                        return;
                    }
                    if (r.status === 400 || body.code === 400) {
                        showToast('保存失败：' + (body.error || '参数错误'));
                        return;
                    }
                    if (r.status !== 200 && body.code !== 200) {
                        showToast('保存失败');
                        return;
                    }
                    input.value = '';   // 明文即清，不缓存
                    edit.remove();
                    showToast('✅ 已保存 ' + it.key);
                    loadKeys();          // 刷新掩码显示
                })
                .catch(function (err) { showToast('保存失败: ' + err.message); });
            }, { confirmText: '覆盖' });
        });
        btns.appendChild(cancelBtn);
        btns.appendChild(saveBtn);
        edit.appendChild(input);
        edit.appendChild(btns);
        row.appendChild(edit);
        input.focus();
    }

    function loadKeys() {
        if (!keysListEl) return;
        const seq = ++keysFetchSeq;   // 竞态守卫（与设置页同口径）
        fetch('/api/keys')
            .then(function (res) { return res.json(); })
            .then(function (body) {
                if (seq !== keysFetchSeq) return;
                if (!body || body.code !== 200) {
                    keysListEl.innerHTML = '';
                    appendKeysTip('权限不足（需要 Lv.3）或读取失败');
                    return;
                }
                renderKeysItems(body);
            })
            .catch(function (err) {
                if (seq !== keysFetchSeq) return;
                keysListEl.innerHTML = '';
                appendKeysTip('密钥读取失败: ' + err.message);
            });
    }

    // 入口探针（LV3+ 门，页面加载即定）：200 → 显 🔑 并预取渲染；
    // 403 → 🔑 hidden（与后端 403 双保险）。
    function probeKeysAccess() {
        if (!keysEntryBtn) return;
        fetch('/api/keys')
            .then(function (res) { return res.json(); })
            .then(function (body) {
                if (body && body.code === 200) {
                    keysEntryBtn.hidden = false;
                    SETTINGS_STATE.level = body.level;   // #264 B2c a：连点判级用（早于设置页）
                    renderKeysItems(body);   // 预取渲染（pane 打开即有内容）
                } else {
                    keysEntryBtn.hidden = true;
                }
            })
            .catch(function () { keysEntryBtn.hidden = true; });
    }

    window.__xiaoju3Console = {
        switchTab: switchChatTab,
        setPetMinimized: setPetMinimized,
        toggleTheme: toggleTheme,
        openAbout: openAbout,
        quitApp: quitApp,
    };

    const PROACTIVE_REASON_LABELS = {
        daily_quota: '今日次数已用完', cooldown: '刚聊过（冷却中）',
        quiet_hours: '深夜时段', rejected: '刚被拒绝过',
        user_busy: '主人忙碌', explicit_stop: '主人说了别烦',
    };

    // ---- 审计三层视图（2026-10-13：不看流水，看"每天干了什么"）----
    // 层 1 日汇总（默认）→ 层 2 当日区间（同分类合并）→ 层 3 原始行。
    function classifyAudit(item) {
        if (item.decision === 'fire') {
            return { key: 'fire', icon: '🔥', label: '出手' };
        }
        const r = item.reason || '';
        if (r.indexOf('quiet_hours') !== -1) {
            return { key: 'quiet', icon: '💤', label: '深夜静默' };
        }
        if (r.indexOf('daily_quota') !== -1) {
            return { key: 'quota', icon: '🚫', label: '配额拦截' };
        }
        if (r.indexOf('explicit_stop') !== -1) {
            return { key: 'stop', icon: '🚫', label: '主人说了别烦' };
        }
        if (r.indexOf('rejected') !== -1) {
            return { key: 'rej', icon: '🚫', label: '被拒后抑制' };
        }
        if (r.indexOf('cooldown') !== -1) {
            return { key: 'cool', icon: '⏸', label: '冷却' };
        }
        if (r.indexOf('user_busy') !== -1) {
            return { key: 'busy', icon: '⏸', label: '主人忙碌' };
        }
        return { key: 'hold', icon: '🟡', label: '按住' };
    }

    function groupAuditByDay(itemsAsc) {
        // ASC 时序 → [{date, items}]（保持 ASC，渲染层再倒序天）
        const days = [];
        itemsAsc.forEach(function (it) {
            const day = (it.ts || '').slice(0, 10);
            if (!days.length || days[days.length - 1].date !== day) {
                days.push({ date: day, items: [] });
            }
            days[days.length - 1].items.push(it);
        });
        return days;
    }

    function mergeAuditRuns(itemsAsc) {
        // 同分类连续 → 区间 {cls, start, end, count}
        const runs = [];
        itemsAsc.forEach(function (it) {
            const cls = classifyAudit(it);
            const last = runs[runs.length - 1];
            if (last && last.cls.key === cls.key) {
                last.end = it.ts;
                last.count += 1;
                last.items.push(it);
            } else {
                runs.push({ cls: cls, start: it.ts, end: it.ts,
                            count: 1, items: [it] });
            }
        });
        return runs;
    }

    function renderProactiveInto(bodyEl) {
        // 面板版主动性监控：三层视图（limit=2000 跨天聚合）
        fetch('/api/proactive/recent?limit=2000')
            .then(function (r) { return r.json(); })
            .then(function (j) {
                const d = (j && j.data) || {};
                bodyEl.textContent = '';
                if (!d.enabled) {
                    bodyEl.textContent = '主动性引擎未启用';
                    return;
                }
                const noteEl = document.createElement('div');
                noteEl.style.cssText = 'font-size:12px;opacity:.7;margin-bottom:6px;';
                noteEl.textContent = '内账观察期：「出手」=仅写审计记录，暂不发真消息。';
                bodyEl.appendChild(noteEl);
                const head = document.createElement('div');
                head.className = 'settings-empty';
                head.textContent = '今日出手 ' + (d.today_fire_count || 0) + '/' +
                    (d.daily_limit || 5) + ' · 当前张力 ' + (d.tension || 0);
                bodyEl.appendChild(head);
                // 频率调节（迁移保全：/api/proactive/config admin 门）
                const tuneRow = document.createElement('div');
                tuneRow.style.cssText = 'display:flex;gap:6px;align-items:center;margin:4px 0 8px;';
                const num = document.createElement('input');
                num.type = 'number'; num.min = '1'; num.max = '50';
                num.value = d.daily_limit || 5;
                num.style.cssText = 'width:70px;';
                tuneRow.appendChild(num);
                const tuneBtn = document.createElement('button');
                tuneBtn.textContent = '保存每天最多主动次数';
                tuneBtn.style.cssText = 'font-size:12px;cursor:pointer;';
                tuneBtn.addEventListener('click', function () {
                    fetch('/api/proactive/config', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ daily_limit: parseInt(num.value, 10) }),
                    }).then(function (r) {
                        return r.json().then(function (j) { return { ok: r.ok, j: j }; });
                    }).then(function (res) {
                        showToast(res.ok ? ('已保存（' + res.j.data.daily_limit + ' 次/天）')
                                          : (res.j.error || '保存失败'));
                        renderProactiveInto(bodyEl);
                    }).catch(function () { showToast('保存失败'); });
                });
                tuneRow.appendChild(tuneBtn);
                bodyEl.appendChild(tuneRow);

                // ---- 三层聚合（recent DESC → 反转 ASC 处理）----
                const itemsAsc = (d.recent || []).slice().reverse();
                const days = groupAuditByDay(itemsAsc).slice().reverse();
                days.forEach(function (day) {
                    const runs = mergeAuditRuns(day.items);
                    const per = {};
                    day.items.forEach(function (it) {
                        const k = classifyAudit(it).key;
                        per[k] = (per[k] || 0) + 1;
                    });
                    const iconOrder = [['fire', '🔥', '出手'], ['hold', '🟡', '按住'],
                                       ['quiet', '💤', '深夜'], ['cool', '⏸', '冷却'],
                                       ['quota', '🚫', '配额'], ['rej', '🚫', '被拒'],
                                       ['stop', '🚫', '别烦'], ['busy', '⏸', '忙碌']];
                    const parts = iconOrder
                        .filter(function (p) { return per[p[0]]; })
                        .map(function (p) { return p[1] + ' ' + p[2] + ' ' + per[p[0]] + ' 次'; });
                    const dayDetail = document.createElement('details');
                    dayDetail.style.cssText = 'margin:4px 0;border:1px solid '
                        + 'var(--color-border,#e0e4ec);border-radius:8px;padding:6px 8px;';
                    const daySum = document.createElement('summary');
                    daySum.style.cssText = 'cursor:pointer;font-size:13px;';
                    daySum.textContent = '📅 ' + day.date + '　' + parts.join(' · ');
                    dayDetail.appendChild(daySum);
                    runs.forEach(function (run) {
                        const st = (run.start || '').slice(11, 16);
                        const en = (run.end || '').slice(11, 16);
                        const mins = Math.round(
                            (new Date(run.end.replace('T', ' ').replace('-', '/'))
                             - new Date(run.start.replace('T', ' ').replace('-', '/'))) / 60000);
                        const runDetail = document.createElement('details');
                        runDetail.style.cssText = 'margin:3px 0 3px 12px;';
                        const runSum = document.createElement('summary');
                        runSum.style.cssText = 'cursor:pointer;font-size:12px;';
                        runSum.textContent = run.cls.icon + ' ' + st + ' - ' + en +
                            '　' + run.cls.label + (run.count > 1
                            ? '（' + run.count + ' 条' +
                              (mins > 0 ? ' / ' + mins + ' 分钟' : '') + '）' : '');
                        runDetail.appendChild(runSum);
                        run.items.forEach(function (it) {
                            const raw = document.createElement('div');
                            raw.style.cssText = 'font-size:11px;opacity:.75;'
                                + 'margin:2px 0 2px 14px;';
                            raw.textContent = (it.ts || '').slice(11) + ' · ' +
                                (it.reason || '') +
                                (it.events ? ' · ' + it.events : '');
                            runDetail.appendChild(raw);
                        });
                        dayDetail.appendChild(runDetail);
                    });
                    bodyEl.appendChild(dayDetail);
                });
            })
            .catch(function () { bodyEl.textContent = '审计读取失败'; });
    }


    // ── 连接手机：二维码配对弹窗（桌面侧，2026-10-29 队长拍板） ──
    // /api/pairing/info 取局域网 IP → xiaoju3://connect?ips=..&port=..
    // → qrcode()（vendored）生成 SVG 展示；多 IP 全部编进一条码，手机端
    // 逐个探活自动挑通的那个。
    function openPairQrModal() {
        fetch('/api/pairing/info')
            .then(function (r) { return r.json(); })
            .then(function (res) {
                const d = res.data || {};
                const ips = (d.ips && d.ips.length ? d.ips : ['127.0.0.1']);
                const port = d.port || 5003;
                const payload = 'xiaoju3://connect?ips='
                    + encodeURIComponent(ips.join(',')) + '&port=' + port;
                let svg = '';
                try {
                    const qr = qrcode(0, 'M');
                    qr.addData(payload);
                    qr.make();
                    svg = qr.createSvgTag({ cellSize: 5, margin: 2 });
                } catch (e) {
                    showToast('二维码生成失败：' + e.message);
                    return;
                }
                const overlay = document.createElement('div');
                overlay.className = 'xj3-modal-overlay';
                const card = document.createElement('div');
                card.className = 'xj3-modal-card';
                card.style.cssText += 'text-align:center;';
                const titleEl = document.createElement('div');
                titleEl.className = 'xj3-modal-title';
                titleEl.style.cssText += 'margin-right:0;';
                titleEl.textContent = '手机扫码连接';
                const msgEl = document.createElement('p');
                msgEl.className = 'xj3-modal-msg';
                msgEl.textContent = '打开手机上的小橘 App →「扫码连接」，'
                    + '对准这个二维码即可。同一 WiFi（或 Tailscale）内有效。';
                const qrBox = document.createElement('div');
                qrBox.style.cssText = 'margin:14px auto 0;width:240px;';
                qrBox.innerHTML = svg;
                const ipLine = document.createElement('div');
                ipLine.style.cssText = 'font-size:12px;color:#9ca3af;margin-top:8px;'
                    + 'word-break:break-all;';
                ipLine.textContent = ips.join(' / ') + ':' + port;
                const doneBtn = document.createElement('button');
                doneBtn.className = 'xj3-modal-btn xj3-modal-btn-secondary';
                doneBtn.style.cssText += 'margin-top:14px;';
                doneBtn.textContent = '完成';
                doneBtn.addEventListener('click', function () { overlay.remove(); });
                card.appendChild(titleEl);
                card.appendChild(msgEl);
                card.appendChild(qrBox);
                card.appendChild(ipLine);
                card.appendChild(doneBtn);
                overlay.appendChild(card);
                overlay.addEventListener('click', function (e) {
                    if (e.target === overlay) overlay.remove();
                });
                document.body.appendChild(overlay);
            })
            .catch(function () { showToast('配对信息获取失败'); });
    }

    function buildToolCard(title, hint, onClick) {
        const card = document.createElement('div');
        card.className = 'tool-card';
        card.style.cssText = 'background:var(--color-card,#fff);'
            + 'border:1px solid var(--color-border,#e0e4ec);'
            + 'border-radius:var(--radius-card,12px);padding:14px 16px;'
            + 'cursor:pointer;box-shadow:var(--shadow-card,0 2px 8px rgba(0,0,0,.06));';
        card.addEventListener('click', onClick);
        const t = document.createElement('div');
        t.style.cssText = 'font-weight:700;font-size:14px;margin-bottom:4px;';
        t.textContent = title;
        card.appendChild(t);
        const h = document.createElement('div');
        h.style.cssText = 'font-size:12px;opacity:.65;';
        h.textContent = hint;
        card.appendChild(h);
        return card;
    }

    function toggleToolBody(bodyId, loader) {
        let body = document.getElementById(bodyId);
        const overlay = document.getElementById('tools-overlay');
        if (!overlay) return;
        if (!body) {
            body = document.createElement('div');
            body.id = bodyId;
            body.hidden = true;   // 新建默认收起，走下方统一展开+加载
            body.style.cssText = 'margin:10px 0 20px;background:var(--color-card,'
                + '#fff);border:1px solid var(--color-border,#e0e4ec);'
                + 'border-radius:var(--radius-card,12px);padding:12px 14px;'
                + 'max-height:60vh;overflow-y:auto;';
            overlay.appendChild(body);
        }
        if (!body.hidden) {
            body.hidden = true;
            return;
        }
        body.hidden = false;
        loader(body);
    }

    function loadMemoryInto(body) {
        body.textContent = '加载中…';
        fetch('/api/memory/list').then(function (r) { return r.json(); })
            .then(function (j) {
                const items = (j.data && j.data.items) || [];
                body.textContent = '';
                if (!items.length) {
                    body.textContent = '长期记忆为空（对我说「记住…」即可积累）';
                    return;
                }
                items.forEach(function (m) {
                    const line = document.createElement('div');
                    line.style.cssText = 'font-size:12px;padding:4px 0;'
                        + 'border-bottom:1px dashed var(--color-border,#e0e4ec);';
                    const sink = m.sink_status === 'pending_sink' ? ' 💤沉睡' : '';
                    const emo = m.emotion_tag !== 'neutral'
                        ? ' 🏷' + m.emotion_tag : '';
                    line.textContent = '· [' + m.category + '] ' + m.content +
                        '（权重 ' + (m.weight || 1) + emo + sink + '）';
                    body.appendChild(line);
                });
            })
            .catch(function () { body.textContent = '记忆读取失败'; });
    }

    // 🔌 插件管理面板（2026-10-28 一期）：列表+独立启停开关（POST toggle
    // → loader 原子换装即时生效）；禁用区单独渲染（可重新启用）。操作反馈
    // 即时（toast+重拉清单），不触碰核心后台进程。
    function loadPluginsManageInto(body) {
        body.textContent = '加载中…';
        fetch('/api/plugins').then(function (r) { return r.json(); })
            .then(function (d) {
                body.textContent = '';
                const wrap = document.createElement('div');
                const mkRow = function (p, enabled) {
                    const row = document.createElement('div');
                    row.style.cssText = 'display:flex;align-items:center;'
                        + 'gap:10px;padding:7px 0;border-bottom:1px dashed '
                        + 'var(--color-border,#e0e4ec);';
                    const info = document.createElement('div');
                    info.style.cssText = 'flex:1;min-width:0;';
                    info.innerHTML = '🧩 <b>' + escapeHtml(p.name) + '</b>'
                        + ' <span class="dp-sub">v' + escapeHtml(p.version || '')
                        + ' · 工具 ' + (p.tools || 0) + '</span><br>'
                        + '<span class="dp-sub">' + escapeHtml(p.desc || '')
                        + '</span>';
                    const badge = document.createElement('span');
                    badge.style.cssText = 'font-size:11px;padding:2px 8px;'
                        + 'border-radius:10px;'
                        + (enabled ? 'background:#e6f6ea;color:#1a7f37;'
                                   : 'background:#f0f0f2;color:#888;');
                    badge.textContent = enabled ? '已启用' : '已停用';
                    const btn = document.createElement('button');
                    btn.className = 'btn btn-small';
                    btn.textContent = enabled ? '停用' : '启用';
                    btn.addEventListener('click', function () {
                        btn.disabled = true;
                        btn.textContent = '切换中…';
                        fetch('/api/plugins/toggle', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({name: p.name,
                                                  enabled: !enabled})
                        }).then(function (r) { return r.json(); })
                          .then(function (j) {
                              if (j.ok) {
                                  showToast('插件 ' + p.name + ' 已'
                                            + (j.enabled ? '启用' : '停用'));
                              } else {
                                  showToast('切换失败：' + (j.error || '未知'));
                              }
                              loadPluginsManageInto(body);   // 重拉即时反馈
                          })
                          .catch(function () {
                              showToast('切换请求失败');
                              loadPluginsManageInto(body);
                          });
                    });
                    row.appendChild(info);
                    row.appendChild(badge);
                    row.appendChild(btn);
                    return row;
                };
                (d.plugins || []).forEach(function (p) {
                    wrap.appendChild(mkRow(p, true));
                });
                (d.disabled || []).forEach(function (name) {
                    wrap.appendChild(mkRow({name: name, version: '',
                                            desc: '（停用中：工具/意图/后台'
                                                  + '线程全部停摆）', tools: 0},
                                           false));
                });
                if (!(d.plugins || []).length && !(d.disabled || []).length) {
                    wrap.innerHTML = '<div class="dp-sub">暂无外部插件</div>';
                }
                const tip = document.createElement('div');
                tip.className = 'dp-sub';
                tip.style.marginTop = '8px';
                tip.textContent = '停用=卸载插件（工具/意图/后台线程全停，'
                                + '持久化重启不回弹）；启用=即时换装。'
                                + '拒绝载入：'
                                + ((d.plugins || []).length ? '' : '见上方')
                                + (d.disabled || []).length + ' 项禁用中。';
                wrap.appendChild(tip);
                body.appendChild(wrap);
            })
            .catch(function () { body.textContent = '清单获取失败'; });
    }

    // 🐾 桌宠开关（2026-10-28 队长拍板默认关）：ui_pref.desktop_pet_enabled
    // → /api/pet_pref GET/POST；切换后刷新页面生效（脚本按配置动态注入）。
    function loadHaDevicesInto(body) {
        body.textContent = '加载中…（HA 可达约需 1-10s）';
        fetch('/api/ha/devices').then(function (r) { return r.json(); })
            .then(function (j) {
                body.textContent = '';
                const pre = document.createElement('pre');
                pre.style.cssText = 'white-space:pre-wrap;font-size:12px;'
                    + 'margin:0;font-family:inherit;';
                pre.textContent = (j.data && j.data.text) || '（空）';
                body.appendChild(pre);
            })
            .catch(function (e) { body.textContent = '读取失败: ' + e; });
    }

    function closeToolsPanel() {
        const overlay = document.getElementById('tools-overlay');
        if (overlay) {
            overlay.hidden = true;
            overlay.textContent = '';
        }
    }

    function openToolsPanel() {
        const overlay = document.getElementById('tools-overlay');
        if (!overlay) return;
        overlay.hidden = false;
        overlay.style.cssText = 'position:fixed;inset:0;z-index:2147482000;'
            + 'background:var(--color-bg,#f4f6f9);overflow-y:auto;padding:18px 22px;';
        overlay.textContent = '';

        const top = document.createElement('div');
        top.style.cssText = 'display:flex;align-items:center;gap:12px;'
            + 'margin-bottom:16px;';
        const back = document.createElement('button');
        back.className = 'header-btn';
        back.textContent = '← 返回';
        back.addEventListener('click', closeToolsPanel);
        top.appendChild(back);
        const title = document.createElement('div');
        title.style.cssText = 'font-size:18px;font-weight:700;';
        title.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-3px;margin-right:4px"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>小工具面板';
        top.appendChild(title);
        overlay.appendChild(top);

        function sectionLabel(text, icon) {
            const s = document.createElement('div');
            s.style.cssText = 'font-weight:700;font-size:13px;opacity:.7;'
                + 'margin:14px 0 8px;display:flex;align-items:center;gap:6px;';
            if (icon) {
                const ic = document.createElement('span');
                ic.style.cssText = 'display:inline-flex;align-items:center;';
                ic.innerHTML = icon;
                s.appendChild(ic);
            }
            const txt = document.createElement('span');
            txt.textContent = text;
            s.appendChild(txt);
            overlay.appendChild(s);
        }
        function grid() {
            const g = document.createElement('div');
            g.style.cssText = 'display:grid;grid-template-columns:'
                + 'repeat(auto-fill,minmax(220px,1fr));gap:12px;';
            overlay.appendChild(g);
            return g;
        }
        function note(text) {
            const n = document.createElement('div');
            n.style.cssText = 'font-size:12px;opacity:.7;margin:8px 0 4px;';
            n.textContent = text;
            overlay.appendChild(n);
            return n;
        }

        // 📊 小橘监控
        sectionLabel('小橘监控', ICON_SVGS.chart);
        const g1 = grid();
        const proBody = document.createElement('div');
        proBody.style.cssText = 'margin:10px 0 20px;';
        g1.appendChild(buildToolCard('主动性监控', '张力/配额/审计（跃迁日志）',
            function () {
                // 卡片点击=就地展开（二次点击收起）
                if (proBody.hidden) {
                    proBody.hidden = false;
                    renderProactiveInto(proBody);
                } else {
                    proBody.hidden = true;
                    proBody.textContent = '';
                }
            }));
        overlay.appendChild(proBody);
        proBody.hidden = true;
        g1.appendChild(buildToolCard('记忆查看', '内容+权重/状态（长期记忆清单）',
            function () { toggleToolBody('tool-memory-body', loadMemoryInto); }));
        g1.appendChild(buildToolCard('终端记录', '终端通道聊天记录（只读）',
            function () {
                closeToolsPanel();
                switchChatTab('terminal');
            }));

        // 🏠 小橘能控制什么
        sectionLabel('小橘能控制什么', ICON_SVGS.house);
        const g2 = grid();
        g2.appendChild(buildToolCard('家电列表', 'HA 实体清单（只读，控制走对话）',
            function () { toggleToolBody('tool-ha-body', loadHaDevicesInto); }));

        // 🔌 管理
        sectionLabel('管理', ICON_SVGS.plug);
        const g3 = grid();
        g3.appendChild(buildToolCard('设置', '权限分级配置/界面偏好/密钥管理',
            function () {
                closeToolsPanel();
                switchChatTab('settings');
            }));
        g3.appendChild(buildToolCard('插件管理', '外部插件启停（停用即卸载，重启用即时换装）',
            function () { toggleToolBody('tool-plugins-body', loadPluginsManageInto); }));
        g3.appendChild(buildToolCard('连接手机', '生成二维码——手机小橘 App 扫码即连',
            function () { openPairQrModal(); }));
        g3.appendChild(_buildPetCard());
        note('面板骨架批 1：监控三类中「主动性监控」可用；其余卡片为占位。');
    }

    // 🐾 桌宠管理卡（自包含展开式：Toggle 内嵌在卡片内，不外溢到面板底部）
    function _buildPetCard() {
        const card = document.createElement('div');
        card.style.cssText = 'background:var(--color-card,#fff);'
            + 'border:1px solid var(--color-border,#e0e4ec);'
            + 'border-radius:var(--radius-card,12px);padding:16px;'
            + 'box-shadow:var(--shadow-card,0 1px 4px rgba(0,0,0,0.06));'
            + 'cursor:pointer;user-select:none;';

        const title = document.createElement('div');
        title.style.cssText = 'font-size:14px;font-weight:700;margin-bottom:4px;';
        title.textContent = '桌面宠物';
        const hint = document.createElement('div');
        hint.style.cssText = 'font-size:12px;color:var(--color-text-hint,#999);';
        hint.textContent = '桌宠开关（默认关）▶ 点击展开';
        card.appendChild(title);
        card.appendChild(hint);

        const body = document.createElement('div');
        body.style.cssText = 'display:none;margin-top:12px;';
        card.appendChild(body);

        let expanded = false;
        let loaded = false;

        card.addEventListener('click', function () {
            expanded = !expanded;
            body.style.display = expanded ? 'block' : 'none';
            hint.textContent = expanded ? '桌宠开关（默认关）▼ 点击收起' : '桌宠开关（默认关）▶ 点击展开';
            if (expanded && !loaded) {
                loaded = true;
                _renderPetToggles(body);
            }
        });

        return card;
    }

    function _renderPetToggles(container) {
        container.textContent = '加载中…';
        fetch('/api/pet_pref').then(function (r) { return r.json(); })
            .then(function (j) {
                const d = j.data || {};
                container.textContent = '';

                const items = [
                    { key: 'desktop_pet_enabled',  label: '🐾 显示桌宠', sub: '独立窗口狐狸挂件' },
                    { key: 'desktop_pet_topmost',  label: '📌 窗口置顶', sub: '始终在最前层' },
                    { key: 'desktop_pet_drag',     label: '🖱️ 允许拖拽', sub: '按住狐狸拖到任意位置' },
                ];

                items.forEach(function (item) {
                    const enabled = !!d[item.key];
                    const row = document.createElement('div');
                    row.className = 'pet-setting-row';

                    const info = document.createElement('div');
                    const lab = document.createElement('div');
                    lab.className = 'pet-setting-label';
                    lab.textContent = item.label;
                    const sub = document.createElement('div');
                    sub.className = 'pet-setting-sub';
                    sub.textContent = item.sub;
                    info.appendChild(lab);
                    info.appendChild(sub);

                    const toggle = document.createElement('label');
                    toggle.className = 'toggle-switch';
                    const cb = document.createElement('input');
                    cb.type = 'checkbox';
                    cb.checked = enabled;
                    const slider = document.createElement('span');
                    slider.className = 'toggle-slider';
                    toggle.appendChild(cb);
                    toggle.appendChild(slider);

                    cb.addEventListener('change', function () {
                        const val = cb.checked;
                        cb.disabled = true;
                        fetch('/api/pet_pref', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify([{key: item.key, value: val}])
                        }).then(function (r) { return r.json(); })
                          .then(function () { cb.disabled = false; })
                          .catch(function () { cb.checked = !val; cb.disabled = false; });
                    });

                    row.appendChild(info);
                    row.appendChild(toggle);
                    container.appendChild(row);
                });

                const tip = document.createElement('div');
                tip.className = 'pet-setting-sub';
                tip.style.marginTop = '8px';
                tip.textContent = '💡 切换后刷新页面生效（独立窗口进程由桌面启动器管理）';
                container.appendChild(tip);
            })
            .catch(function () { container.textContent = '读取失败'; });
    }

    // 🧰 入口绑定（header-actions 最前，齿轮/密钥同款 header-btn）
    const toolsEntry = document.getElementById('tools-entry');
    if (toolsEntry) {
        toolsEntry.addEventListener('click', openToolsPanel);
    }
    // 🔄 强制刷新（清缓存+重载，2026-10-29 队长要求）
    const refreshBtn = document.getElementById('force-refresh');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function () {
            window.location.reload(true);
        });
    }
})();

    // ==================== 小工具面板（MAA 式收纳，2026-10-13 批 1） ====================
    // 顶部 🧰 → 全屏 overlay 卡片墙（三分类）；主动性监控卡=首批实装
    // （从设置页迁入：折叠摘要+展开审计列表，跃迁日志后端复用）。
    // 终端记录/记忆查看/家电列表=批 2；插件管理=批 3（#312）。
