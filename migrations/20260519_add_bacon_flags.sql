IF SCHEMA_ID(N'lab') IS NULL
    EXEC(N'CREATE SCHEMA lab');
GO

IF OBJECT_ID(N'lab.muestras', N'U') IS NULL
    THROW 50000, 'No existe la tabla lab.muestras. Crear la tabla base antes de aplicar esta migracion.', 1;
GO

IF COL_LENGTH(N'lab.muestras', N'bacon_recibido') IS NULL
BEGIN
    ALTER TABLE lab.muestras
        ADD bacon_recibido bit NOT NULL
            CONSTRAINT DF_muestras_bacon_recibido DEFAULT (0);
END
GO

IF COL_LENGTH(N'lab.muestras', N'bacon_pdf_enviado') IS NULL
BEGIN
    ALTER TABLE lab.muestras
        ADD bacon_pdf_enviado bit NOT NULL
            CONSTRAINT DF_muestras_bacon_pdf_enviado DEFAULT (0);
END
GO
