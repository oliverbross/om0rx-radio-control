/*M!999999\- enable the sandbox mode */ 
-- MariaDB dump 10.19  Distrib 10.6.22-MariaDB, for debian-linux-gnu (x86_64)
--
-- Host: 127.0.0.1    Database: om0rx
-- ------------------------------------------------------
-- Server version	10.6.22-MariaDB-0ubuntu0.22.04.1

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Current Database: `om0rx`
--

CREATE DATABASE /*!32312 IF NOT EXISTS*/ `om0rx` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci */;

USE `om0rx`;

--
-- Table structure for table `TABLE_HRD_CONTACTS_V01`
--

DROP TABLE IF EXISTS `TABLE_HRD_CONTACTS_V01`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `TABLE_HRD_CONTACTS_V01` (
  `COL_PRIMARY_KEY` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `COL_ADDRESS` varchar(255) DEFAULT NULL,
  `COL_AGE` int(11) DEFAULT NULL,
  `COL_A_INDEX` double DEFAULT NULL,
  `COL_ANT_AZ` double DEFAULT NULL,
  `COL_ANT_EL` double DEFAULT NULL,
  `COL_ANT_PATH` varchar(2) DEFAULT NULL,
  `COL_ARRL_SECT` varchar(10) DEFAULT NULL,
  `COL_BAND` varchar(10) DEFAULT NULL,
  `COL_BAND_RX` varchar(10) DEFAULT NULL,
  `COL_BIOGRAPHY` longtext DEFAULT NULL,
  `COL_CALL` varchar(32) DEFAULT NULL,
  `COL_CHECK` varchar(8) DEFAULT NULL,
  `COL_CLASS` varchar(8) DEFAULT NULL,
  `COL_CNTY` varchar(32) DEFAULT NULL,
  `COL_CNTY_ALT` varchar(255) DEFAULT NULL,
  `COL_COMMENT` longtext DEFAULT NULL,
  `COL_CONT` varchar(6) DEFAULT NULL,
  `COL_CONTACTED_OP` varchar(32) DEFAULT NULL,
  `COL_CONTEST_ID` varchar(32) DEFAULT NULL,
  `COL_COUNTRY` varchar(64) DEFAULT NULL,
  `COL_CQZ` int(11) DEFAULT NULL,
  `COL_DISTANCE` double DEFAULT NULL,
  `COL_DXCC` varchar(6) DEFAULT NULL,
  `COL_EMAIL` varchar(255) DEFAULT NULL,
  `COL_EQ_CALL` varchar(32) DEFAULT NULL,
  `COL_EQSL_QSLRDATE` datetime DEFAULT NULL,
  `COL_EQSL_QSLSDATE` datetime DEFAULT NULL,
  `COL_EQSL_QSL_RCVD` varchar(2) DEFAULT NULL,
  `COL_EQSL_QSL_SENT` varchar(2) DEFAULT NULL,
  `COL_EQSL_STATUS` varchar(255) DEFAULT NULL,
  `COL_EQSL_AG` varchar(10) DEFAULT NULL,
  `COL_FORCE_INIT` varchar(2) DEFAULT NULL,
  `COL_FREQ` bigint(13) DEFAULT NULL,
  `COL_FREQ_RX` bigint(13) DEFAULT NULL,
  `COL_GRIDSQUARE` varchar(12) DEFAULT NULL,
  `COL_HEADING` double DEFAULT NULL,
  `COL_IOTA` varchar(10) DEFAULT NULL,
  `COL_ITUZ` int(11) DEFAULT NULL,
  `COL_K_INDEX` double DEFAULT NULL,
  `COL_LAT` varchar(15) DEFAULT NULL,
  `COL_LON` varchar(15) DEFAULT NULL,
  `COL_LOTW_QSLRDATE` datetime DEFAULT NULL,
  `COL_LOTW_QSLSDATE` datetime DEFAULT NULL,
  `COL_LOTW_QSL_RCVD` varchar(2) DEFAULT NULL,
  `COL_LOTW_QSL_SENT` varchar(2) DEFAULT NULL,
  `COL_LOTW_STATUS` varchar(255) DEFAULT NULL,
  `COL_MAX_BURSTS` int(11) DEFAULT NULL,
  `COL_MODE` varchar(12) DEFAULT NULL,
  `COL_MS_SHOWER` varchar(32) DEFAULT NULL,
  `COL_MY_CITY` varchar(32) DEFAULT NULL,
  `COL_MY_CNTY` varchar(32) DEFAULT NULL,
  `COL_MY_CNTY_ALT` varchar(255) DEFAULT NULL,
  `COL_MY_COUNTRY` varchar(64) DEFAULT NULL,
  `COL_MY_CQ_ZONE` int(11) DEFAULT NULL,
  `COL_MY_GRIDSQUARE` varchar(12) DEFAULT NULL,
  `COL_MY_IOTA` varchar(10) DEFAULT NULL,
  `COL_MY_ITU_ZONE` int(11) DEFAULT NULL,
  `COL_MY_LAT` varchar(15) DEFAULT NULL,
  `COL_MY_LON` varchar(15) DEFAULT NULL,
  `COL_MY_NAME` varchar(64) DEFAULT NULL,
  `COL_MY_POSTAL_CODE` varchar(24) DEFAULT NULL,
  `COL_MY_RIG` varchar(255) DEFAULT NULL,
  `COL_MY_SIG` varchar(64) DEFAULT NULL,
  `COL_MY_SIG_INFO` varchar(128) DEFAULT NULL,
  `COL_MY_STATE` varchar(32) DEFAULT NULL,
  `COL_MY_STREET` varchar(64) DEFAULT NULL,
  `COL_NAME` varchar(128) DEFAULT NULL,
  `COL_NOTES` longtext DEFAULT NULL,
  `COL_NR_BURSTS` int(11) DEFAULT NULL,
  `COL_NR_PINGS` int(11) DEFAULT NULL,
  `COL_OPERATOR` varchar(32) DEFAULT NULL,
  `COL_OWNER_CALLSIGN` varchar(32) DEFAULT NULL,
  `COL_PFX` varchar(32) DEFAULT NULL,
  `COL_PRECEDENCE` varchar(32) DEFAULT NULL,
  `COL_PROP_MODE` varchar(8) DEFAULT NULL,
  `COL_PUBLIC_KEY` varchar(255) DEFAULT NULL,
  `COL_QSLMSG` varchar(255) DEFAULT NULL,
  `COL_QSLMSG_RCVD` varchar(255) DEFAULT NULL,
  `COL_QSLRDATE` datetime DEFAULT NULL,
  `COL_QSLSDATE` datetime DEFAULT NULL,
  `COL_QSL_RCVD` varchar(2) DEFAULT NULL,
  `COL_QSL_RCVD_VIA` varchar(2) DEFAULT NULL,
  `COL_QSL_SENT` varchar(2) DEFAULT NULL,
  `COL_QSL_SENT_VIA` varchar(2) DEFAULT NULL,
  `COL_QSL_VIA` varchar(255) DEFAULT NULL,
  `COL_QSO_COMPLETE` varchar(6) DEFAULT NULL,
  `COL_QSO_RANDOM` int(11) DEFAULT NULL,
  `COL_QTH` varchar(128) DEFAULT NULL,
  `COL_RIG` varchar(255) DEFAULT NULL,
  `COL_RST_RCVD` varchar(32) DEFAULT NULL,
  `COL_RST_SENT` varchar(32) DEFAULT NULL,
  `COL_RX_PWR` double DEFAULT NULL,
  `COL_SAT_MODE` varchar(32) DEFAULT NULL,
  `COL_SAT_NAME` varchar(32) DEFAULT NULL,
  `COL_SFI` double DEFAULT NULL,
  `COL_SIG` varchar(64) DEFAULT NULL,
  `COL_SIG_INFO` varchar(128) DEFAULT NULL,
  `COL_SRX` int(11) DEFAULT NULL,
  `COL_SRX_STRING` varchar(32) DEFAULT NULL,
  `COL_STATE` varchar(32) DEFAULT NULL,
  `COL_STATION_CALLSIGN` varchar(32) DEFAULT NULL,
  `COL_STX` int(11) DEFAULT NULL,
  `COL_STX_STRING` varchar(32) DEFAULT NULL,
  `COL_SWL` varchar(2) DEFAULT NULL,
  `COL_TEN_TEN` int(11) DEFAULT NULL,
  `COL_TIME_OFF` datetime DEFAULT NULL,
  `COL_TIME_ON` datetime DEFAULT NULL,
  `COL_TX_PWR` double DEFAULT NULL,
  `COL_WEB` varchar(128) DEFAULT NULL,
  `COL_USER_DEFINED_0` varchar(64) DEFAULT NULL,
  `COL_USER_DEFINED_1` varchar(64) DEFAULT NULL,
  `COL_USER_DEFINED_2` varchar(64) DEFAULT NULL,
  `COL_USER_DEFINED_3` varchar(64) DEFAULT NULL,
  `COL_USER_DEFINED_4` varchar(64) DEFAULT NULL,
  `COL_USER_DEFINED_5` varchar(64) DEFAULT NULL,
  `COL_USER_DEFINED_6` varchar(64) DEFAULT NULL,
  `COL_USER_DEFINED_7` varchar(64) DEFAULT NULL,
  `COL_USER_DEFINED_8` varchar(64) DEFAULT NULL,
  `COL_USER_DEFINED_9` varchar(64) DEFAULT NULL,
  `COL_CREDIT_GRANTED` varchar(64) DEFAULT NULL,
  `COL_CREDIT_SUBMITTED` varchar(64) DEFAULT NULL,
  `COL_ADDRESS_INTL` varchar(255) DEFAULT NULL,
  `COL_AWARD_GRANTED` varchar(255) DEFAULT NULL,
  `COL_AWARD_SUBMITTED` varchar(255) DEFAULT NULL,
  `COL_CLUBLOG_QSO_UPLOAD_DATE` datetime DEFAULT NULL,
  `COL_CLUBLOG_QSO_UPLOAD_STATUS` varchar(20) DEFAULT NULL,
  `COL_COMMENT_INTL` varchar(255) DEFAULT NULL,
  `COL_COUNTRY_INTL` varchar(255) DEFAULT NULL,
  `COL_SILENT_KEY` varchar(2) DEFAULT NULL,
  `COL_SKCC` varchar(255) DEFAULT NULL,
  `COL_DARC_DOK` varchar(10) DEFAULT NULL,
  `COL_FISTS` int(10) DEFAULT NULL,
  `COL_FISTS_CC` int(10) DEFAULT NULL,
  `COL_HRDLOG_QSO_UPLOAD_DATE` datetime DEFAULT NULL,
  `COL_HRDLOG_QSO_UPLOAD_STATUS` varchar(10) DEFAULT NULL,
  `COL_MY_ANTENNA` varchar(255) DEFAULT NULL,
  `COL_MY_ANTENNA_INTL` varchar(255) DEFAULT NULL,
  `COL_MY_CITY_INTL` varchar(255) DEFAULT NULL,
  `COL_MY_COUNTRY_INTL` int(6) DEFAULT NULL,
  `COL_MY_DXCC` int(6) DEFAULT NULL,
  `COL_MY_FISTS` int(10) DEFAULT NULL,
  `COL_MY_IOTA_ISLAND_ID` varchar(10) DEFAULT NULL,
  `COL_MY_NAME_INTL` varchar(255) DEFAULT NULL,
  `COL_MY_POSTCODE_INTL` varchar(255) DEFAULT NULL,
  `COL_MY_RIG_INTL` varchar(255) DEFAULT NULL,
  `COL_MY_SIG_INTL` varchar(255) DEFAULT NULL,
  `COL_MY_SIG_INFO_INTL` varchar(255) DEFAULT NULL,
  `COL_MY_SOTA_REF` varchar(50) DEFAULT NULL,
  `COL_MY_STREET_INTL` varchar(255) DEFAULT NULL,
  `COL_MY_USACA_COUNTIES` varchar(255) DEFAULT NULL,
  `COL_MY_VUCC_GRIDS` varchar(50) DEFAULT NULL,
  `COL_NAME_INTL` varchar(255) DEFAULT NULL,
  `COL_NOTES_INTL` longtext DEFAULT NULL,
  `COL_QRZCOM_QSO_UPLOAD_DATE` datetime DEFAULT NULL,
  `COL_QRZCOM_QSO_UPLOAD_STATUS` varchar(10) DEFAULT NULL,
  `COL_QSO_DATE` date DEFAULT NULL,
  `COL_QSO_DATE_OFF` date DEFAULT NULL,
  `COL_QTH_INTL` varchar(255) DEFAULT NULL,
  `COL_REGION` varchar(25) DEFAULT NULL,
  `COL_MORSE_KEY_INFO` varchar(255) DEFAULT NULL,
  `COL_MORSE_KEY_TYPE` varchar(10) DEFAULT NULL,
  `COL_RIG_INTL` varchar(255) DEFAULT NULL,
  `COL_SIG_INTL` varchar(255) DEFAULT NULL,
  `COL_SIG_INFO_INTL` varchar(255) DEFAULT NULL,
  `COL_SOTA_REF` varchar(30) DEFAULT NULL,
  `COL_SUBMODE` varchar(25) DEFAULT NULL,
  `COL_UKSMG` varchar(64) DEFAULT NULL,
  `COL_USACA_COUNTIES` varchar(255) DEFAULT NULL,
  `COL_VUCC_GRIDS` varchar(255) DEFAULT NULL,
  `station_id` int(10) unsigned NOT NULL,
  `COL_WWFF_REF` varchar(30) DEFAULT NULL,
  `COL_MY_WWFF_REF` varchar(50) DEFAULT NULL,
  `COL_POTA_REF` varchar(128) DEFAULT NULL,
  `COL_MY_POTA_REF` varchar(128) DEFAULT NULL,
  `COL_MY_DARC_DOK` varchar(10) DEFAULT NULL,
  `COL_QRZCOM_QSO_DOWNLOAD_DATE` datetime DEFAULT NULL,
  `COL_QRZCOM_QSO_DOWNLOAD_STATUS` varchar(10) DEFAULT NULL,
  `COL_CLUBLOG_QSO_DOWNLOAD_DATE` datetime DEFAULT NULL,
  `COL_CLUBLOG_QSO_DOWNLOAD_STATUS` varchar(10) DEFAULT NULL,
  `COL_DCL_QSLRDATE` datetime DEFAULT NULL,
  `COL_DCL_QSL_RCVD` varchar(10) DEFAULT NULL,
  `COL_DCL_QSLSDATE` datetime DEFAULT NULL,
  `COL_DCL_QSL_SENT` varchar(10) DEFAULT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`COL_PRIMARY_KEY`),
  KEY `HRD_IDX_COL_PROP_MODE` (`COL_PROP_MODE`),
  KEY `COL_SUBMODE` (`COL_SUBMODE`),
  KEY `idx_HRD_DBL_CHK` (`station_id`,`COL_CALL`,`COL_BAND`,`COL_MODE`),
  KEY `idx_HRD_COL_BAND_station_id` (`station_id`,`COL_BAND`,`COL_TIME_ON`),
  KEY `idx_HRD_COL_CALL_station_id` (`station_id`,`COL_CALL`,`COL_TIME_ON`),
  KEY `idx_HRD_COL_DXCC_station_id` (`station_id`,`COL_DXCC`,`COL_TIME_ON`),
  KEY `idx_HRD_station_id` (`station_id`,`COL_TIME_ON`),
  KEY `HRD_IDX_COL_IOTA` (`station_id`,`COL_IOTA`),
  CONSTRAINT `TABLE_HRD_CONTACTS_V01_station_profile_FK` FOREIGN KEY (`station_id`) REFERENCES `station_profile` (`station_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=79646 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `adif_modes`
--

DROP TABLE IF EXISTS `adif_modes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `adif_modes` (
  `id` int(9) NOT NULL AUTO_INCREMENT,
  `mode` varchar(12) NOT NULL,
  `submode` varchar(25) DEFAULT NULL,
  `qrgmode` varchar(4) NOT NULL,
  `active` int(11) NOT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `IDX_UNIQ_ADIF_MODES#mode#submode#qrgmode#active` (`mode`,`submode`,`qrgmode`,`active`)
) ENGINE=InnoDB AUTO_INCREMENT=499 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `api`
--

DROP TABLE IF EXISTS `api`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `api` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `key` varchar(255) NOT NULL,
  `rights` varchar(10) NOT NULL,
  `status` varchar(10) NOT NULL,
  `last_change` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `last_used` timestamp NOT NULL DEFAULT current_timestamp(),
  `description` varchar(255) DEFAULT NULL,
  `user_id` int(10) unsigned NOT NULL,
  `created_by` int(6) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `api_users_FK` (`user_id`),
  CONSTRAINT `api_users_FK` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `bandedges`
--

DROP TABLE IF EXISTS `bandedges`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `bandedges` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `userid` int(11) NOT NULL,
  `frequencyfrom` bigint(20) NOT NULL,
  `frequencyto` bigint(20) NOT NULL,
  `mode` varchar(20) NOT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=89 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `bands`
--

DROP TABLE IF EXISTS `bands`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `bands` (
  `id` int(20) unsigned NOT NULL AUTO_INCREMENT,
  `band` varchar(20) NOT NULL,
  `bandgroup` varchar(20) NOT NULL,
  `ssb` bigint(20) unsigned NOT NULL,
  `data` bigint(20) unsigned NOT NULL,
  `cw` bigint(20) unsigned NOT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=24 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `bandxuser`
--

DROP TABLE IF EXISTS `bandxuser`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `bandxuser` (
  `id` int(20) unsigned NOT NULL AUTO_INCREMENT,
  `bandid` int(20) unsigned NOT NULL,
  `userid` int(20) unsigned NOT NULL,
  `active` tinyint(1) unsigned NOT NULL DEFAULT 1,
  `cq` tinyint(1) unsigned NOT NULL DEFAULT 1,
  `dok` tinyint(1) unsigned NOT NULL DEFAULT 1,
  `dxcc` tinyint(1) unsigned NOT NULL DEFAULT 1,
  `iota` tinyint(1) unsigned NOT NULL DEFAULT 1,
  `sig` tinyint(1) unsigned NOT NULL DEFAULT 1,
  `sota` tinyint(1) unsigned NOT NULL DEFAULT 1,
  `uscounties` tinyint(1) unsigned NOT NULL DEFAULT 1,
  `was` tinyint(1) unsigned NOT NULL DEFAULT 1,
  `vucc` tinyint(1) unsigned NOT NULL DEFAULT 1,
  `wwff` tinyint(1) unsigned NOT NULL DEFAULT 1,
  `pota` tinyint(1) unsigned NOT NULL DEFAULT 1,
  `waja` tinyint(1) unsigned NOT NULL DEFAULT 1,
  `rac` tinyint(1) unsigned NOT NULL DEFAULT 1,
  `helvetia` tinyint(1) unsigned NOT NULL DEFAULT 1,
  `jcc` tinyint(1) unsigned NOT NULL DEFAULT 1,
  `wap` tinyint(4) NOT NULL DEFAULT 1,
  `wapc` tinyint(4) NOT NULL DEFAULT 1,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `id` (`id`),
  KEY `bandxuser_users_FK` (`userid`),
  CONSTRAINT `bandxuser_users_FK` FOREIGN KEY (`userid`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=32 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `cat`
--

DROP TABLE IF EXISTS `cat`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `cat` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `radio` varchar(250) NOT NULL,
  `frequency` bigint(20) DEFAULT NULL,
  `mode` varchar(10) DEFAULT NULL,
  `frequency_rx` bigint(13) DEFAULT NULL,
  `mode_rx` varchar(10) DEFAULT NULL,
  `sat_name` varchar(255) DEFAULT NULL,
  `timestamp` timestamp NULL DEFAULT NULL,
  `user_id` int(10) unsigned NOT NULL,
  `power` int(11) DEFAULT 0,
  `prop_mode` varchar(10) DEFAULT NULL,
  `cat_url` varchar(255) NOT NULL DEFAULT 'http://127.0.0.1:54321',
  `operator` int(6) NOT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `cat_users_FK` (`user_id`),
  CONSTRAINT `cat_users_FK` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `club_permissions`
--

DROP TABLE IF EXISTS `club_permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `club_permissions` (
  `id` int(6) unsigned NOT NULL AUTO_INCREMENT,
  `club_id` int(6) unsigned NOT NULL,
  `user_id` int(6) unsigned NOT NULL,
  `p_level` int(2) unsigned NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `modified_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_id` (`user_id`,`club_id`),
  CONSTRAINT `fk_user_id` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `config`
--

DROP TABLE IF EXISTS `config`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `config` (
  `id` int(9) NOT NULL AUTO_INCREMENT,
  `lotw_download_url` varchar(255) DEFAULT NULL,
  `lotw_upload_url` varchar(255) DEFAULT NULL,
  `lotw_rcvd_mark` varchar(1) DEFAULT NULL,
  `lotw_login_url` varchar(244) DEFAULT NULL,
  `eqsl_download_url` varchar(244) DEFAULT NULL,
  `eqsl_rcvd_mark` varchar(1) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `contest`
--

DROP TABLE IF EXISTS `contest`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `contest` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(256) DEFAULT NULL,
  `adifname` varchar(256) DEFAULT NULL,
  `active` int(11) DEFAULT 1,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_contest_adifname` (`adifname`)
) ENGINE=InnoDB AUTO_INCREMENT=251 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `contest_session`
--

DROP TABLE IF EXISTS `contest_session`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `contest_session` (
  `id` int(20) unsigned NOT NULL AUTO_INCREMENT,
  `contestid` varchar(100) NOT NULL,
  `exchangesent` varchar(20) NOT NULL,
  `serialsent` varchar(20) NOT NULL,
  `qso` varchar(100) NOT NULL,
  `station_id` int(10) unsigned NOT NULL,
  `settings` text DEFAULT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `cron`
--

DROP TABLE IF EXISTS `cron`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `cron` (
  `id` varchar(191) NOT NULL,
  `enabled` tinyint(1) NOT NULL,
  `status` varchar(255) DEFAULT NULL,
  `description` varchar(255) DEFAULT NULL,
  `function` varchar(255) NOT NULL,
  `expression` varchar(100) DEFAULT NULL,
  `last_run` timestamp NULL DEFAULT NULL,
  `next_run` timestamp NULL DEFAULT NULL,
  `modified` timestamp NULL DEFAULT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `cwmacros`
--

DROP TABLE IF EXISTS `cwmacros`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `cwmacros` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) unsigned NOT NULL,
  `station_location_id` bigint(20) unsigned NOT NULL,
  `function1_name` varchar(255) DEFAULT NULL,
  `function1_macro` varchar(255) DEFAULT NULL,
  `function2_name` varchar(255) DEFAULT NULL,
  `function2_macro` varchar(255) DEFAULT NULL,
  `function3_name` varchar(255) DEFAULT NULL,
  `function3_macro` varchar(255) DEFAULT NULL,
  `function4_name` varchar(255) DEFAULT NULL,
  `function4_macro` varchar(255) DEFAULT NULL,
  `function5_name` varchar(255) DEFAULT NULL,
  `function5_macro` varchar(255) DEFAULT NULL,
  `modified` timestamp NULL DEFAULT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`,`user_id`,`station_location_id`),
  UNIQUE KEY `id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `dxcc_entities`
--

DROP TABLE IF EXISTS `dxcc_entities`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `dxcc_entities` (
  `adif` smallint(6) NOT NULL,
  `name` varchar(150) DEFAULT NULL,
  `prefix` varchar(32) NOT NULL,
  `cqz` smallint(6) NOT NULL,
  `ituz` smallint(6) NOT NULL,
  `cont` varchar(5) NOT NULL,
  `long` float NOT NULL,
  `lat` float NOT NULL,
  `end` date DEFAULT NULL,
  `start` date DEFAULT NULL,
  PRIMARY KEY (`adif`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `dxcc_exceptions`
--

DROP TABLE IF EXISTS `dxcc_exceptions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `dxcc_exceptions` (
  `record` int(11) NOT NULL,
  `call` varchar(32) DEFAULT NULL,
  `entity` varchar(255) NOT NULL,
  `adif` smallint(6) NOT NULL,
  `cqz` smallint(6) NOT NULL,
  `cont` varchar(5) NOT NULL,
  `long` float NOT NULL,
  `lat` float NOT NULL,
  `start` date DEFAULT NULL,
  `end` date DEFAULT NULL,
  PRIMARY KEY (`record`),
  KEY `idx_dxcc_exceptions_logic` (`call`,`start`,`end`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `dxcc_master`
--

DROP TABLE IF EXISTS `dxcc_master`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `dxcc_master` (
  `DXCCPrefix` varchar(6) DEFAULT NULL,
  `DXCCSearch` varchar(6) DEFAULT NULL,
  `DXCCMap` varchar(6) DEFAULT NULL,
  `DXCCSort` int(11) DEFAULT 0,
  `CountryCode` int(11) DEFAULT 0,
  `PrefixList` longtext DEFAULT NULL,
  `DXCCName` varchar(30) DEFAULT NULL,
  `Location` varchar(40) DEFAULT NULL,
  `Continent` varchar(2) DEFAULT NULL,
  `CQZone` varchar(2) DEFAULT NULL,
  `ITUZone` varchar(2) DEFAULT NULL,
  `IOTA` varchar(10) DEFAULT NULL,
  `TimeZone` float DEFAULT NULL,
  `Latitude` double DEFAULT NULL,
  `Longitude` double DEFAULT NULL,
  `StartDate` datetime DEFAULT NULL,
  `EndDate` datetime DEFAULT NULL,
  KEY `CountryCode` (`CountryCode`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `dxcc_prefixes`
--

DROP TABLE IF EXISTS `dxcc_prefixes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `dxcc_prefixes` (
  `record` int(11) NOT NULL,
  `call` varchar(32) DEFAULT NULL,
  `entity` varchar(255) NOT NULL,
  `adif` smallint(6) NOT NULL,
  `cqz` smallint(6) NOT NULL,
  `cont` varchar(5) NOT NULL,
  `long` float NOT NULL,
  `lat` float NOT NULL,
  `start` date DEFAULT NULL,
  `end` date DEFAULT NULL,
  PRIMARY KEY (`record`),
  KEY `idx_dxcc_prefixes_logic` (`call`,`start`,`end`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `dxcc_temp`
--

DROP TABLE IF EXISTS `dxcc_temp`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `dxcc_temp` (
  `prefix` varchar(32) NOT NULL,
  `name` varchar(150) DEFAULT NULL,
  `adif` smallint(6) NOT NULL,
  `cont` varchar(5) NOT NULL,
  `cqz` smallint(6) NOT NULL,
  `ituz` smallint(6) NOT NULL,
  `long` float NOT NULL,
  `lat` float NOT NULL,
  `time` smallint(6) DEFAULT NULL,
  PRIMARY KEY (`adif`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `dxpedition`
--

DROP TABLE IF EXISTS `dxpedition`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `dxpedition` (
  `id` int(6) unsigned NOT NULL AUTO_INCREMENT,
  `start_date` date DEFAULT NULL,
  `end_date` date DEFAULT NULL,
  `callsign` varchar(50) NOT NULL,
  `country` varchar(255) DEFAULT NULL,
  `notes` varchar(255) DEFAULT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`,`callsign`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `eQSL_images`
--

DROP TABLE IF EXISTS `eQSL_images`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `eQSL_images` (
  `id` int(5) unsigned NOT NULL AUTO_INCREMENT,
  `qso_id` bigint(20) unsigned NOT NULL,
  `image_file` varchar(250) NOT NULL,
  `modified` timestamp NULL DEFAULT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `qso_id_UNIQUE` (`qso_id`),
  CONSTRAINT `eQSL_images_TABLE_HRD_CONTACTS_V01_FK` FOREIGN KEY (`qso_id`) REFERENCES `TABLE_HRD_CONTACTS_V01` (`COL_PRIMARY_KEY`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=11183 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `hams_of_note`
--

DROP TABLE IF EXISTS `hams_of_note`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `hams_of_note` (
  `id` int(20) unsigned NOT NULL AUTO_INCREMENT,
  `callsign` varchar(32) NOT NULL,
  `description` varchar(256) NOT NULL,
  `linkname` varchar(256) DEFAULT '',
  `link` varchar(256) DEFAULT '',
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `id` (`id`),
  KEY `callsign` (`callsign`)
) ENGINE=InnoDB AUTO_INCREMENT=1371 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `iota`
--

DROP TABLE IF EXISTS `iota`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `iota` (
  `Tag` varchar(8) NOT NULL,
  `Name` longtext DEFAULT NULL,
  `Prefix` varchar(16) DEFAULT NULL,
  `DXCCID` int(11) DEFAULT 0,
  `Lat1` float DEFAULT 0,
  `Lat2` float DEFAULT 0,
  `Lon1` float DEFAULT 0,
  `Lon2` float DEFAULT 0,
  `Status` varchar(1) DEFAULT NULL,
  `Notes` varchar(50) DEFAULT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  UNIQUE KEY `idx_iota_Tag` (`Tag`),
  KEY `DXCCID` (`DXCCID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `label_types`
--

DROP TABLE IF EXISTS `label_types`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `label_types` (
  `id` int(5) unsigned NOT NULL AUTO_INCREMENT,
  `user_id` int(10) unsigned NOT NULL,
  `label_name` varchar(250) NOT NULL,
  `metric` varchar(10) NOT NULL,
  `marginleft` decimal(6,3) DEFAULT NULL,
  `margintop` decimal(6,3) DEFAULT NULL,
  `nx` decimal(6,3) DEFAULT NULL,
  `ny` decimal(6,3) DEFAULT NULL,
  `spacex` decimal(6,3) DEFAULT NULL,
  `spacey` decimal(6,3) DEFAULT NULL,
  `width` decimal(6,3) DEFAULT NULL,
  `height` decimal(6,3) DEFAULT NULL,
  `font_size` int(5) DEFAULT NULL,
  `font` varchar(250) DEFAULT NULL,
  `qsos` int(5) DEFAULT NULL,
  `useforprint` int(5) DEFAULT NULL,
  `last_modified` timestamp NULL DEFAULT NULL,
  `paper_type_id` int(5) NOT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`,`user_id`),
  KEY `label_types_users_FK` (`user_id`),
  CONSTRAINT `label_types_users_FK` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `lotw_certs`
--

DROP TABLE IF EXISTS `lotw_certs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `lotw_certs` (
  `lotw_cert_id` int(1) unsigned NOT NULL AUTO_INCREMENT,
  `callsign` varchar(100) NOT NULL,
  `cert_dxcc_id` smallint(6) NOT NULL DEFAULT 0,
  `date_created` datetime DEFAULT NULL,
  `date_expires` datetime DEFAULT NULL,
  `qso_start_date` datetime DEFAULT NULL,
  `qso_end_date` datetime DEFAULT NULL,
  `cert_key` text DEFAULT NULL,
  `user_id` int(10) unsigned NOT NULL,
  `last_upload` datetime DEFAULT NULL,
  `last_upload_fail` datetime DEFAULT NULL,
  `last_upload_status` varchar(50) DEFAULT NULL,
  `cert` text DEFAULT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`lotw_cert_id`),
  KEY `lotw_certs_users_FK` (`user_id`),
  CONSTRAINT `lotw_certs_users_FK` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `lotw_users`
--

DROP TABLE IF EXISTS `lotw_users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `lotw_users` (
  `id` int(20) unsigned NOT NULL AUTO_INCREMENT,
  `callsign` varchar(32) NOT NULL,
  `lastupload` datetime NOT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `callsign_UNIQUE` (`callsign`)
) ENGINE=InnoDB AUTO_INCREMENT=223485 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `migrations`
--

DROP TABLE IF EXISTS `migrations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `migrations` (
  `version` bigint(20) NOT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `notes`
--

DROP TABLE IF EXISTS `notes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `notes` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `cat` varchar(255) NOT NULL,
  `title` varchar(255) NOT NULL,
  `note` text NOT NULL,
  `user_id` int(10) unsigned NOT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `notes_users_FK` (`user_id`),
  CONSTRAINT `notes_users_FK` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `options`
--

DROP TABLE IF EXISTS `options`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `options` (
  `option_id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `option_name` varchar(191) DEFAULT NULL,
  `option_value` longtext NOT NULL,
  `autoload` varchar(20) DEFAULT NULL,
  PRIMARY KEY (`option_id`),
  UNIQUE KEY `option_name` (`option_name`)
) ENGINE=InnoDB AUTO_INCREMENT=27 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `oqrs`
--

DROP TABLE IF EXISTS `oqrs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `oqrs` (
  `id` int(20) unsigned NOT NULL AUTO_INCREMENT,
  `requesttime` timestamp NOT NULL DEFAULT current_timestamp(),
  `date` date NOT NULL,
  `time` time NOT NULL,
  `band` varchar(10) NOT NULL,
  `mode` varchar(12) NOT NULL,
  `requestcallsign` varchar(32) NOT NULL,
  `station_id` int(10) unsigned NOT NULL,
  `note` text NOT NULL,
  `email` text NOT NULL,
  `qslroute` varchar(50) NOT NULL,
  `status` int(11) NOT NULL,
  `qsoid` bigint(20) unsigned DEFAULT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `id` (`id`),
  UNIQUE KEY `qsoid` (`qsoid`),
  KEY `oqrs_station_profile_FK` (`station_id`),
  CONSTRAINT `oqrs_logbook_fk` FOREIGN KEY (`qsoid`) REFERENCES `TABLE_HRD_CONTACTS_V01` (`COL_PRIMARY_KEY`) ON DELETE CASCADE,
  CONSTRAINT `oqrs_station_profile_FK` FOREIGN KEY (`station_id`) REFERENCES `station_profile` (`station_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `paper_types`
--

DROP TABLE IF EXISTS `paper_types`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `paper_types` (
  `paper_id` int(5) unsigned NOT NULL AUTO_INCREMENT,
  `user_id` int(10) unsigned NOT NULL,
  `paper_name` varchar(191) NOT NULL,
  `metric` varchar(10) NOT NULL,
  `width` decimal(6,3) DEFAULT NULL,
  `orientation` varchar(1) DEFAULT NULL,
  `height` decimal(6,3) DEFAULT NULL,
  `last_modified` timestamp NULL DEFAULT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`paper_id`,`user_id`),
  UNIQUE KEY `idx_paper_types_user_id_paper_name` (`user_id`,`paper_name`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `primary_subdivisions`
--

DROP TABLE IF EXISTS `primary_subdivisions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `primary_subdivisions` (
  `adif` smallint(20) unsigned NOT NULL,
  `state` varchar(20) NOT NULL,
  `subdivision` varchar(250) NOT NULL,
  `deprecated` tinyint(1) DEFAULT 0,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  UNIQUE KEY `IDX_UNIQ_SUBDIVISON#adif#state#deprecated` (`adif`,`state`,`deprecated`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `qsl_images`
--

DROP TABLE IF EXISTS `qsl_images`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `qsl_images` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `qsoid` bigint(20) unsigned NOT NULL,
  `filename` mediumtext DEFAULT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `IDX_QSL_IMAGES_QSOID` (`qsoid`),
  CONSTRAINT `qsl_images_TABLE_HRD_CONTACTS_V01_FK` FOREIGN KEY (`qsoid`) REFERENCES `TABLE_HRD_CONTACTS_V01` (`COL_PRIMARY_KEY`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `queries`
--

DROP TABLE IF EXISTS `queries`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `queries` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `query` mediumtext DEFAULT NULL,
  `description` mediumtext DEFAULT NULL,
  `userid` int(11) NOT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `satellite`
--

DROP TABLE IF EXISTS `satellite`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `satellite` (
  `id` int(6) unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(255) DEFAULT NULL,
  `displayname` varchar(255) DEFAULT NULL,
  `orbit` varchar(255) DEFAULT NULL,
  `lotw` varchar(1) NOT NULL DEFAULT 'N',
  `norad_id` int(9) unsigned DEFAULT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `SAT_IDX_NAME` (`name`),
  KEY `SAT_IDX_ORBIT` (`orbit`)
) ENGINE=InnoDB AUTO_INCREMENT=58 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `satellitemode`
--

DROP TABLE IF EXISTS `satellitemode`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `satellitemode` (
  `id` int(6) unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(255) DEFAULT NULL,
  `satelliteid` int(6) unsigned NOT NULL,
  `uplink_mode` varchar(255) DEFAULT NULL,
  `uplink_freq` varchar(255) DEFAULT NULL,
  `downlink_mode` varchar(255) DEFAULT NULL,
  `downlink_freq` varchar(255) DEFAULT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `satmode_satellite_FK` (`satelliteid`),
  CONSTRAINT `satmode_satellite_FK` FOREIGN KEY (`satelliteid`) REFERENCES `satellite` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=63 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `station_logbooks`
--

DROP TABLE IF EXISTS `station_logbooks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `station_logbooks` (
  `logbook_id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `user_id` int(10) unsigned NOT NULL,
  `logbook_name` varchar(191) DEFAULT NULL,
  `modified` timestamp NULL DEFAULT NULL,
  `public_slug` varchar(191) DEFAULT NULL,
  `public_search` int(11) DEFAULT 0,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`logbook_id`,`user_id`),
  UNIQUE KEY `logbook_id` (`logbook_id`),
  UNIQUE KEY `public_slug` (`public_slug`),
  KEY `station_logbooks_users_FK` (`user_id`),
  CONSTRAINT `station_logbooks_users_FK` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `station_logbooks_relationship`
--

DROP TABLE IF EXISTS `station_logbooks_relationship`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `station_logbooks_relationship` (
  `logbook_relation_id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `station_logbook_id` int(10) unsigned NOT NULL,
  `station_location_id` int(10) unsigned NOT NULL,
  `modified` timestamp NULL DEFAULT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`logbook_relation_id`,`station_logbook_id`,`station_location_id`),
  UNIQUE KEY `logbook_relation_id` (`logbook_relation_id`),
  KEY `station_logbooks_relationship_station_profile_FK` (`station_location_id`),
  CONSTRAINT `station_logbooks_relationship_station_profile_FK` FOREIGN KEY (`station_location_id`) REFERENCES `station_profile` (`station_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `station_profile`
--

DROP TABLE IF EXISTS `station_profile`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `station_profile` (
  `station_id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `station_profile_name` varchar(200) NOT NULL,
  `station_gridsquare` varchar(100) NOT NULL,
  `station_city` varchar(100) NOT NULL,
  `station_iota` varchar(100) NOT NULL,
  `station_sota` varchar(10) NOT NULL,
  `station_callsign` varchar(50) DEFAULT NULL,
  `station_power` smallint(6) DEFAULT NULL,
  `station_dxcc` int(10) DEFAULT NULL,
  `station_cnty` varchar(200) DEFAULT NULL,
  `station_cq` int(5) DEFAULT NULL,
  `station_itu` int(5) DEFAULT NULL,
  `station_active` tinyint(1) DEFAULT NULL,
  `eqslqthnickname` varchar(255) DEFAULT NULL,
  `state` varchar(4) DEFAULT NULL,
  `qrzapikey` varchar(20) DEFAULT NULL,
  `county` varchar(255) DEFAULT NULL,
  `station_sig` varchar(64) DEFAULT NULL,
  `station_sig_info` varchar(128) DEFAULT NULL,
  `qrzrealtime` tinyint(1) DEFAULT 0,
  `user_id` int(10) unsigned NOT NULL,
  `station_wwff` varchar(50) DEFAULT NULL,
  `station_pota` varchar(50) DEFAULT NULL,
  `oqrs` int(11) DEFAULT 0,
  `oqrs_text` text DEFAULT NULL,
  `oqrs_email` int(11) DEFAULT 0,
  `webadifapikey` varchar(50) DEFAULT NULL,
  `webadifapiurl` varchar(256) DEFAULT NULL,
  `webadifrealtime` tinyint(1) DEFAULT 0,
  `clublogignore` tinyint(4) NOT NULL DEFAULT 0,
  `clublogrealtime` tinyint(4) NOT NULL DEFAULT 0,
  `hrdlogrealtime` tinyint(1) DEFAULT NULL,
  `hrdlog_code` varchar(20) DEFAULT NULL,
  `hrdlog_username` varchar(20) DEFAULT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`station_id`),
  KEY `station_profile_users_FK` (`user_id`),
  CONSTRAINT `station_profile_users_FK` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `themes`
--

DROP TABLE IF EXISTS `themes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `themes` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(256) NOT NULL,
  `foldername` varchar(256) NOT NULL,
  `header_logo` varchar(50) DEFAULT 'wavelog_icon_only_default',
  `main_logo` varchar(50) DEFAULT 'wavelog_logo_default',
  `theme_mode` varchar(20) DEFAULT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `thirdparty_logins`
--

DROP TABLE IF EXISTS `thirdparty_logins`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `thirdparty_logins` (
  `service_id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) unsigned NOT NULL,
  `service_name` varchar(255) DEFAULT NULL,
  `service_password` varchar(255) DEFAULT NULL,
  `active` tinyint(1) DEFAULT NULL,
  `modified` timestamp NULL DEFAULT NULL,
  `service_username` varchar(255) DEFAULT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`service_id`,`user_id`),
  UNIQUE KEY `service_id` (`service_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `timezones`
--

DROP TABLE IF EXISTS `timezones`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `timezones` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `offset` decimal(3,1) NOT NULL,
  `name` varchar(120) NOT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=151 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tle`
--

DROP TABLE IF EXISTS `tle`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tle` (
  `id` int(6) unsigned NOT NULL AUTO_INCREMENT,
  `satelliteid` int(6) unsigned NOT NULL,
  `tle` text DEFAULT NULL,
  `updated` timestamp NOT NULL DEFAULT current_timestamp(),
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`satelliteid`),
  UNIQUE KEY `tle_unique_id` (`id`),
  CONSTRAINT `tle_satellite_FK` FOREIGN KEY (`satelliteid`) REFERENCES `satellite` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=23 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `user_options`
--

DROP TABLE IF EXISTS `user_options`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_options` (
  `user_id` int(10) unsigned NOT NULL,
  `option_type` varchar(45) NOT NULL,
  `option_name` varchar(45) NOT NULL,
  `option_key` varchar(45) NOT NULL,
  `option_value` text DEFAULT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`user_id`,`option_type`,`option_key`,`option_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `user_id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `user_name` varchar(32) NOT NULL COMMENT 'Username',
  `user_password` varchar(64) NOT NULL COMMENT 'Password',
  `user_email` varchar(64) NOT NULL COMMENT 'E-mail address',
  `user_type` varchar(8) NOT NULL COMMENT 'User type',
  `clubstation` tinyint(1) DEFAULT 0,
  `user_callsign` varchar(32) NOT NULL COMMENT 'User''s callsign',
  `user_locator` varchar(16) NOT NULL COMMENT 'User''s locator',
  `user_firstname` varchar(32) NOT NULL COMMENT 'User''s first name',
  `user_lastname` varchar(32) NOT NULL COMMENT 'User''s last name',
  `user_timezone` int(3) NOT NULL DEFAULT 0,
  `user_lotw_name` varchar(32) DEFAULT NULL,
  `user_lotw_password` varchar(64) DEFAULT NULL,
  `user_eqsl_name` varchar(32) DEFAULT NULL,
  `user_eqsl_password` varchar(64) DEFAULT NULL,
  `user_eqsl_qth_nickname` varchar(32) DEFAULT NULL,
  `active_station_logbook` int(11) DEFAULT NULL,
  `user_language` varchar(32) DEFAULT NULL,
  `user_clublog_name` varchar(255) DEFAULT NULL,
  `user_clublog_password` varchar(255) DEFAULT NULL,
  `user_clublog_callsign` varchar(255) DEFAULT NULL,
  `user_measurement_base` varchar(1) DEFAULT 'K',
  `user_date_format` varchar(15) DEFAULT 'd/m/y',
  `user_stylesheet` varchar(255) DEFAULT 'bootstrap.min.css',
  `user_sota_lookup` int(11) DEFAULT 0,
  `user_wwff_lookup` int(11) DEFAULT 0,
  `user_pota_lookup` int(11) DEFAULT 0,
  `user_qth_lookup` int(11) DEFAULT 0,
  `user_show_notes` int(11) DEFAULT 1,
  `user_column1` varchar(32) DEFAULT 'Mode',
  `user_column2` varchar(32) DEFAULT 'RSTS',
  `user_column3` varchar(32) DEFAULT 'RSTR',
  `user_column4` varchar(32) DEFAULT 'Band',
  `user_column5` varchar(32) DEFAULT 'Country',
  `reset_password_code` varchar(50) DEFAULT NULL,
  `reset_password_date` timestamp NULL DEFAULT NULL,
  `last_seen` timestamp NULL DEFAULT NULL,
  `user_show_profile_image` tinyint(1) DEFAULT 0,
  `user_previous_qsl_type` int(11) DEFAULT 0,
  `user_amsat_status_upload` tinyint(1) DEFAULT 0,
  `user_mastodon_url` varchar(32) DEFAULT NULL,
  `user_default_band` varchar(10) DEFAULT NULL,
  `user_default_confirmation` varchar(10) DEFAULT NULL,
  `user_quicklog_enter` int(11) DEFAULT 0,
  `user_quicklog` int(11) DEFAULT 0,
  `user_qso_end_times` int(11) DEFAULT 0,
  `winkey` tinyint(1) DEFAULT 0,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `modified_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `login_attempts` int(11) DEFAULT 0,
  `slug` varchar(50) NOT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `user_name` (`user_name`),
  UNIQUE KEY `user_email` (`user_email`),
  UNIQUE KEY `user_slug_unique` (`slug`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Temporary table structure for view `vw_qsos_effective`
--

DROP TABLE IF EXISTS `vw_qsos_effective`;
/*!50001 DROP VIEW IF EXISTS `vw_qsos_effective`*/;
SET @saved_cs_client     = @@character_set_client;
SET character_set_client = utf8mb4;
/*!50001 CREATE VIEW `vw_qsos_effective` AS SELECT
 1 AS `own_station`,
  1 AS `dxcall`,
  1 AS `dxcc`,
  1 AS `band`,
  1 AS `emode`,
  1 AS `lotw` */;
SET character_set_client = @saved_cs_client;

--
-- Table structure for table `webadif`
--

DROP TABLE IF EXISTS `webadif`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `webadif` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `qso_id` int(11) NOT NULL,
  `upload_date` datetime NOT NULL,
  `creation_date` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_modified` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `qso_id_upload_date` (`qso_id`,`upload_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping events for database 'om0rx'
--

--
-- Dumping routines for database 'om0rx'
--

--
-- Current Database: `om0rx`
--

USE `om0rx`;

--
-- Final view structure for view `vw_qsos_effective`
--

/*!50001 DROP VIEW IF EXISTS `vw_qsos_effective`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_general_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`wavelog`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `vw_qsos_effective` AS select ucase(trim(`TABLE_HRD_CONTACTS_V01`.`COL_STATION_CALLSIGN`)) AS `own_station`,ucase(trim(`TABLE_HRD_CONTACTS_V01`.`COL_CALL`)) AS `dxcall`,cast(`TABLE_HRD_CONTACTS_V01`.`COL_DXCC` as unsigned) AS `dxcc`,`TABLE_HRD_CONTACTS_V01`.`COL_BAND` AS `band`,coalesce(nullif(`TABLE_HRD_CONTACTS_V01`.`COL_SUBMODE`,''),`TABLE_HRD_CONTACTS_V01`.`COL_MODE`) AS `emode`,`TABLE_HRD_CONTACTS_V01`.`COL_LOTW_QSL_RCVD` AS `lotw` from `TABLE_HRD_CONTACTS_V01` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2025-11-04 17:51:02
