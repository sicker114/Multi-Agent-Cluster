package com.enterprise.agent.common.utils;

import cn.hutool.core.io.IoUtil;
import cn.hutool.core.util.StrUtil;
import com.enterprise.agent.common.exception.BusinessException;
import com.enterprise.agent.common.response.ResultCode;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.text.PDFTextStripper;
import org.apache.poi.hwpf.HWPFDocument;
import org.apache.poi.hwpf.extractor.WordExtractor;
import org.apache.poi.xwpf.extractor.XWPFWordExtractor;
import org.apache.poi.xwpf.usermodel.XWPFDocument;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

/**
 * 文档文本抽取工具：支持 PDF / DOC / DOCX / TXT，抽取纯文本内容。
 * <p>供文件读取接口在返回给 Python GraphRAG 前抽取正文并脱敏。</p>
 *
 * @author enterprise-agent
 */
public final class DocumentExtractUtil {

    private DocumentExtractUtil() {
    }

    /**
     * 按文件类型抽取纯文本。
     *
     * @param inputStream 文件输入流（方法内部负责关闭）
     * @param fileType    文件类型 pdf/doc/docx/txt
     * @return 抽取的文本内容
     */
    public static String extract(InputStream inputStream, String fileType) {
        if (StrUtil.isBlank(fileType)) {
            throw new BusinessException(ResultCode.FILE_TYPE_NOT_SUPPORT);
        }
        try (InputStream in = inputStream) {
            return switch (fileType.toLowerCase()) {
                case "pdf" -> extractPdf(in);
                case "docx" -> extractDocx(in);
                case "doc" -> extractDoc(in);
                case "txt" -> IoUtil.read(in, StandardCharsets.UTF_8);
                default -> throw new BusinessException(ResultCode.FILE_TYPE_NOT_SUPPORT);
            };
        } catch (BusinessException e) {
            throw e;
        } catch (Exception e) {
            throw new BusinessException(ResultCode.FILE_READ_FAILED, "文档解析失败：" + e.getMessage());
        }
    }

    private static String extractPdf(InputStream in) throws Exception {
        byte[] bytes = IoUtil.readBytes(in, false);
        try (PDDocument document = Loader.loadPDF(bytes)) {
            PDFTextStripper stripper = new PDFTextStripper();
            return stripper.getText(document);
        }
    }

    private static String extractDocx(InputStream in) throws Exception {
        try (XWPFDocument doc = new XWPFDocument(in);
             XWPFWordExtractor extractor = new XWPFWordExtractor(doc)) {
            return extractor.getText();
        }
    }

    private static String extractDoc(InputStream in) throws Exception {
        try (HWPFDocument doc = new HWPFDocument(in);
             WordExtractor extractor = new WordExtractor(doc)) {
            return extractor.getText();
        }
    }
}
