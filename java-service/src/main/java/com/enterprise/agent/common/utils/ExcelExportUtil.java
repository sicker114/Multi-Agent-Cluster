package com.enterprise.agent.common.utils;

import com.enterprise.agent.entity.BizQaHistory;
import org.apache.poi.ss.usermodel.*;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;

import java.io.ByteArrayOutputStream;
import java.time.format.DateTimeFormatter;
import java.util.List;

/**
 * Excel 导出工具：将问答历史/分析报告导出为 xlsx。
 *
 * @author enterprise-agent
 */
public final class ExcelExportUtil {

    private ExcelExportUtil() {
    }

    private static final DateTimeFormatter DTF = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    /**
     * 导出问答历史列表为 Excel 字节数组。
     *
     * @param records 问答历史
     * @return xlsx 字节数组
     */
    public static byte[] exportQaHistory(List<BizQaHistory> records) {
        try (Workbook workbook = new XSSFWorkbook();
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            Sheet sheet = workbook.createSheet("分析报告历史");

            // 表头样式
            CellStyle headerStyle = workbook.createCellStyle();
            Font headerFont = workbook.createFont();
            headerFont.setBold(true);
            headerStyle.setFont(headerFont);
            headerStyle.setFillForegroundColor(IndexedColors.GREY_25_PERCENT.getIndex());
            headerStyle.setFillPattern(FillPatternType.SOLID_FOREGROUND);

            String[] headers = {"记录ID", "会话ID", "问题", "分析报告", "置信度", "风险标注",
                    "重试次数", "Token消耗", "命中缓存", "耗时(ms)", "状态", "创建时间"};
            Row headerRow = sheet.createRow(0);
            for (int i = 0; i < headers.length; i++) {
                Cell cell = headerRow.createCell(i);
                cell.setCellValue(headers[i]);
                cell.setCellStyle(headerStyle);
            }

            int rowIdx = 1;
            for (BizQaHistory r : records) {
                Row row = sheet.createRow(rowIdx++);
                row.createCell(0).setCellValue(r.getId() == null ? "" : String.valueOf(r.getId()));
                row.createCell(1).setCellValue(nullSafe(r.getSessionId()));
                row.createCell(2).setCellValue(nullSafe(r.getQuestion()));
                row.createCell(3).setCellValue(nullSafe(r.getAnswerReport()));
                row.createCell(4).setCellValue(r.getConfidenceScore() == null ? 0 : r.getConfidenceScore());
                row.createCell(5).setCellValue(nullSafe(r.getRiskTags()));
                row.createCell(6).setCellValue(r.getRetryCount() == null ? 0 : r.getRetryCount());
                row.createCell(7).setCellValue(r.getTokenCost() == null ? 0 : r.getTokenCost());
                row.createCell(8).setCellValue(r.getCacheHit() != null && r.getCacheHit() == 1 ? "是" : "否");
                row.createCell(9).setCellValue(r.getCostMs() == null ? 0 : r.getCostMs());
                row.createCell(10).setCellValue(nullSafe(r.getStatus()));
                row.createCell(11).setCellValue(r.getCreateTime() == null ? "" : r.getCreateTime().format(DTF));
            }

            // 列宽自适应（限制最大宽度，避免报告列过宽）
            for (int i = 0; i < headers.length; i++) {
                sheet.autoSizeColumn(i);
                int width = Math.min(sheet.getColumnWidth(i), 60 * 256);
                sheet.setColumnWidth(i, width);
            }

            workbook.write(out);
            return out.toByteArray();
        } catch (Exception e) {
            throw new RuntimeException("Excel 导出失败：" + e.getMessage(), e);
        }
    }

    private static String nullSafe(String s) {
        return s == null ? "" : s;
    }
}
