# EPOS / DSEA QTIL SECOM (`0xEB 0xFE`) Complete Command Table

Statically extracted from `dciadapter.dll` (`epos::dci::QtilSecomparserGenerated` vftable, EPOS Connect 8.7.0.52713).
Total commands extracted: **171**.

## Key Breakthrough: Hidden H3PRO Hybrid Voice Prompts / Tones Control

- **`0x07 / 0x01` (`Tone_SetAudioPromptsMode`)** & **`0x07 / 0x05` (`Tone_GetAudioPromptsMode`)**
  - `1` = `AudioNotificationsVoicePrompts` (Spoken voice prompts)
  - `2` = `AudioNotificationsTones` (Sound effects / chimes only — *"Tu-DU" / "Tu-di"*, no spoken voice)
  - `0` = `AudioNotificationsOff` (Silent)
  - Verified live on **EPOS H3PRO Hybrid (`1395:0101`, fw `1.3.5`)**: `GET` returned `1`, `SET(2)` returned `0` (`STATUS_SUCCESS`), `GET` confirmed `2`.

## Complete Extracted Command Map

| Group | Cmd | vft Offset | Method Name (`QtilSecomparserGenerated`) | H3PRO Status |
|-------|-----|------------|------------------------------------------|--------------|
| `0x01` | `0x03` | `+0x264` | `Service_GetSwVersion` | VERIFIED LIVE (fw v1.3.5) |
| `0x01` | `0x04` | `+0x268` | `Service_GetProtocolVersion` |  |
| `0x01` | `0x05` | `+0x26c` | `Service_GetSerial` |  |
| `0x01` | `0x06` | `+0x270` | `Service_EnterDfu` |  |
| `0x01` | `0x08` | `+0x274` | `Service_GetNumberOfSubDevices` |  |
| `0x01` | `0x09` | `+0x278` | `Service_GetSubDevicesConnected` | VERIFIED (Dongle connected) |
| `0x01` | `0x0A` | `+0x27c` | `Service_SerialSet` |  |
| `0x01` | `0x0B` | `+0x280` | `Service_SerialGet` |  |
| `0x01` | `0x0D` | `+0x284` | `Service_GetDfuType` |  |
| `0x01` | `0x10` | `+0x288` | `Service_GetDeviceId` |  |
| `0x01` | `0x13` | `+0x28c` | `Service_FactoryReset` |  |
| `0x01` | `0x14` | `+0x290` | `Service_GetProductIdNumber` |  |
| `0x01` | `0x16` | `+0x294` | `Service_GetSystemReleaseVersion` |  |
| `0x01` | `0x1A` | `+0x298` | `Service_ProductionReset` |  |
| `0x01` | `0x1F` | `+0x29c` | `Service_EnableDisableAutoPowerOffTimer` | VERIFIED (Set Auto-Sleep) |
| `0x01` | `0x20` | `+0x2a0` | `Service_GetAutoPowerOffTimerStatus` | VERIFIED LIVE (Get Auto-Sleep) |
| `0x01` | `0x21` | `+0x2a4` | `Service_SetAutoPowerOffTimerValue` |  |
| `0x01` | `0x22` | `+0x2a8` | `Service_GetAutoPowerOffTimerValue` | VERIFIED LIVE (30 min) |
| `0x01` | `0x2E` | `+0x2ac` | `Service_GetVendorIdNumber` |  |
| `0x01` | `0x2F` | `+0x2b0` | `Service_ConfigureAutoPausePCMusicOnPCCall` |  |
| `0x01` | `0x30` | `+0x2b4` | `Service_GetAutoPausePCMusicOnPCCallStatus` |  |
| `0x05` | `0x1D` | `+0x240` | `Call_ConfigureCallMerge` |  |
| `0x05` | `0x1E` | `+0x244` | `Call_ConfigureRingFeatureSupport` |  |
| `0x05` | `0x1F` | `+0x248` | `Call_GetRingFeatureSupport` |  |
| `0x05` | `0x22` | `+0x24c` | `Call_SetPreLinklossNotificationSupport` |  |
| `0x05` | `0x23` | `+0x250` | `Call_GetPreLinklossNotificationSupport` |  |
| `0x05` | `0x24` | `+0x254` | `Call_SetSpeechEnhancement` |  |
| `0x05` | `0x25` | `+0x258` | `Call_GetSpeechEnhancement` |  |
| `0x05` | `0x26` | `+0x25c` | `Call_ConfigureAutoResumeHeldCallAfterEndActiveCall` |  |
| `0x05` | `0x27` | `+0x260` | `Call_GetAutoResumeHeldCallAfterEndActiveCallStatus` |  |
| `0x06` | `0x06` | `+0x1b8` | `Device_OverrideLinkPolicy` |  |
| `0x06` | `0x09` | `+0x1bc` | `Device_EnablePairing` |  |
| `0x06` | `0x0B` | `+0x1c0` | `Device_Disconnect` |  |
| `0x06` | `0x10` | `+0x1c4` | `Device_GetConnectedDeviceBdAddr` |  |
| `0x06` | `0x11` | `+0x1c8` | `Device_GetNbrLinkKeys` |  |
| `0x06` | `0x13` | `+0x1cc` | `Device_ClearLinkKeys` |  |
| `0x06` | `0x14` | `+0x1d0` | `Device_GetBdAddr` |  |
| `0x06` | `0x1A` | `+0x1d4` | `Device_EventControl` |  |
| `0x06` | `0x1C` | `+0x1d8` | `Device_CancelPairingMode` |  |
| `0x06` | `0x20` | `+0x1dc` | `Device_ConfigureBtSupport` |  |
| `0x06` | `0x21` | `+0x1e0` | `Device_GetBtSupportStatus` |  |
| `0x06` | `0x22` | `+0x1e4` | `Device_GetRemoteAGAttributeValues` |  |
| `0x06` | `0x23` | `+0x1e8` | `Device_LockUnlockRemoteDevice` |  |
| `0x06` | `0x24` | `+0x1ec` | `Device_GetDevicePdlMode` |  |
| `0x06` | `0x25` | `+0x1f0` | `Device_SetDevicePdlMode` |  |
| `0x06` | `0x26` | `+0x1f4` | `Device_SetBtLocalName` |  |
| `0x06` | `0x27` | `+0x1f8` | `Device_GetBtLocalName` |  |
| `0x06` | `0x28` | `+0x1fc` | `Device_ConfigureDevicePdlModeMmi` |  |
| `0x06` | `0x2A` | `+0x200` | `Device_DeletePairedDevice` |  |
| `0x06` | `0x2B` | `+0x204` | `Device_ConfigureClearPairingListMmi` |  |
| `0x06` | `0x2C` | `+0x208` | `Device_GetClearPairingListMmiSupport` |  |
| `0x06` | `0x2D` | `+0x20c` | `Device_ConfigureFactoryResetMmi` |  |
| `0x06` | `0x2E` | `+0x210` | `Device_GetFactoryResetMmiSupport` |  |
| `0x06` | `0x2F` | `+0x214` | `Device_GetDeviceAudioMode` |  |
| `0x06` | `0x30` | `+0x218` | `Device_SetMultipointConnectionInSco` |  |
| `0x06` | `0x31` | `+0x21c` | `Device_GetMultipointConnectionInSco` |  |
| `0x06` | `0x32` | `+0x220` | `Device_GetRemoteDeviceInfo` |  |
| `0x06` | `0x45` | `+0x224` | `Device_GetDevicePdlModeMmiState` |  |
| `0x06` | `0x4E` | `+0x228` | `Device_GetDeviceState` |  |
| `0x06` | `0x51` | `+0x22c` | `Device_DisplayName` |  |
| `0x06` | `0x52` | `+0x230` | `Device_ProductGuid` |  |
| `0x06` | `0x54` | `+0x234` | `Device_SetLMPRoleSwitchConfiguration` |  |
| `0x06` | `0x55` | `+0x238` | `Device_GetLMPRoleSwitchConfiguration` |  |
| `0x06` | `0x59` | `+0x23c` | `Device_GetDeviceLinkInfo` |  |
| `0x07` | `0x01` | `+0x198` | `Tone_SetAudioPromptsMode` | VERIFIED LIVE (1=Voice, 2=Tones SFX, 0=Off) |
| `0x07` | `0x02` | `+0x19c` | `Tone_SetVpLanguage` |  |
| `0x07` | `0x03` | `+0x1a0` | `Tone_GetVpLanguage` | VERIFIED LIVE (Language=0) |
| `0x07` | `0x05` | `+0x1a4` | `Tone_GetAudioPromptsMode` | VERIFIED LIVE (1->2 persisted) |
| `0x07` | `0x08` | `+0x1a8` | `Tone_ConfigureAudiopromptsModeMMI` |  |
| `0x07` | `0x09` | `+0x1ac` | `Tone_EnableDisableProductSoundsDuringCall` |  |
| `0x07` | `0x0A` | `+0x1b0` | `Tone_GetProductSoundsDuringCallStatus` |  |
| `0x07` | `0x0B` | `+0x1b4` | `Tone_GetAudiopromptsModeMMI` |  |
| `0x08` | `0x1D` | `+0x160` | `Input_ConfigureBoomArmMMIAction` |  |
| `0x08` | `0x1E` | `+0x164` | `Input_GetBoomArmMMIActionState` |  |
| `0x08` | `0x1F` | `+0x168` | `Input_ConfigureDockUndockMMIAction` |  |
| `0x08` | `0x20` | `+0x16c` | `Input_GetDockUndockMMIActionState` |  |
| `0x08` | `0x21` | `+0x170` | `Input_SetMMIActions` |  |
| `0x08` | `0x22` | `+0x174` | `Input_GetMMIActions` |  |
| `0x08` | `0x24` | `+0x178` | `Input_GetCustomEQConfiguration` |  |
| `0x08` | `0x25` | `+0x17c` | `Input_SetCustomEQBandLevel` |  |
| `0x08` | `0x26` | `+0x180` | `Input_GetCustomEQBandLevel` |  |
| `0x08` | `0x27` | `+0x184` | `Input_ConfigureButtonControl` |  |
| `0x08` | `0x28` | `+0x188` | `Input_GetButtonControl` |  |
| `0x08` | `0xEF` | `+0x18c` | `Input_Proximity_SetMode` |  |
| `0x08` | `0xEF` | `+0x190` | `Input_Proximity_ConfigureMMI` |  |
| `0x08` | `0xF0` | `+0x194` | `Input_Events_Control` |  |
| `0x09` | `0x01` | `+0x150` | `USB_GetProductString` |  |
| `0x09` | `0x02` | `+0x154` | `USB_GetManufacturerString` |  |
| `0x09` | `0x05` | `+0x158` | `USB_SetIncomingCallRingtoneType` |  |
| `0x09` | `0x06` | `+0x15c` | `USB_GetIncomingCallRingtoneType` |  |
| `0x0A` | `0x03` | `+0x104` | `Sound_SetExternalisation` |  |
| `0x0A` | `0x04` | `+0x108` | `Sound_GetExternalisation` |  |
| `0x0A` | `0x07` | `+0x10c` | `Sound_SetPreset` |  |
| `0x0A` | `0x08` | `+0x110` | `Sound_GetPreset` |  |
| `0x0A` | `0x0B` | `+0x114` | `Sound_SetSideToneGain` | VERIFIED (Set Sidetone 0..255) |
| `0x0A` | `0x0C` | `+0x118` | `Sound_GetSideToneGain` | VERIFIED LIVE (Get Sidetone) |
| `0x0A` | `0x11` | `+0x11c` | `Sound_SetNoiseReduction` | VERIFIED (Set Mic Noise Filter) |
| `0x0A` | `0x12` | `+0x120` | `Sound_GetNoiseReduction` | VERIFIED LIVE (Get Mic Noise Filter) |
| `0x0A` | `0x14` | `+0x124` | `Sound_SetVolumeLimiter` |  |
| `0x0A` | `0x15` | `+0x128` | `Sound_GetVolumeLimiter` |  |
| `0x0A` | `0x16` | `+0x12c` | `Sound_SetSecomBidirAudioLinkLatency` |  |
| `0x0A` | `0x17` | `+0x130` | `Sound_GetSecomBidirAudioLinkLatency` |  |
| `0x0A` | `0x1A` | `+0x134` | `Sound_SetPcSoundPriority` |  |
| `0x0A` | `0x1B` | `+0x138` | `Sound_GetPcSoundPriority` |  |
| `0x0A` | `0x1C` | `+0x13c` | `Sound_ConfigurePcSoundPriorityMmi` |  |
| `0x0A` | `0x23` | `+0x140` | `Sound_EnableDisableNormalizer` |  |
| `0x0A` | `0x24` | `+0x144` | `Sound_GetNormalizer` |  |
| `0x0A` | `0x2A` | `+0x148` | `Sound_SetDictationMode` |  |
| `0x0A` | `0x2B` | `+0x14c` | `Sound_GetDictationMode` |  |
| `0x10` | `0x1B` | `+0x0e8` | `SpeakerMic_SetOptimizedMicSetting` |  |
| `0x10` | `0x1C` | `+0x0ec` | `SpeakerMic_GetOptimizedMicSetting` |  |
| `0x10` | `0x1E` | `+0x0f0` | `SpeakerMic_ConfigureOptimizedMicSettingMmi` |  |
| `0x10` | `0x2D` | `+0x0f4` | `SpeakerMic_SetBoomArmPlacement` |  |
| `0x10` | `0x2E` | `+0x0f8` | `SpeakerMic_GetBoomArmPlacement` |  |
| `0x10` | `0x2F` | `+0x0fc` | `SpeakerMic_SetTalkWhileMuteLedIndication` |  |
| `0x10` | `0x30` | `+0x100` | `SpeakerMic_GetTalkWhileMuteLedIndication` |  |
| `0x11` | `0x01` | `+0x0dc` | `Flash_GetPSKey` |  |
| `0x11` | `0x02` | `+0x0e0` | `Flash_SetPSKey` |  |
| `0x11` | `0x05` | `+0x0e4` | `Flash_GetGeneralSettings` |  |
| `0x12` | `0x01` | `+0x0c8` | `Battery_GetBatteryVoltageLevel` | VERIFIED LIVE (4158 mV, level 5) |
| `0x12` | `0x02` | `+0x0cc` | `Battery_GetChargingStatus` | VERIFIED LIVE (Charging status=5) |
| `0x12` | `0x03` | `+0x0d0` | `Battery_GetBatteryPercent` | VERIFIED LIVE (Battery 100%) |
| `0x12` | `0x05` | `+0x0d4` | `Battery_GetLevelAndState` |  |
| `0x12` | `0x0F` | `+0x0d8` | `Battery_Events_Control` |  |
| `0x13` | `0x01` | `+0x0b4` | `Boot_GetBootMode` |  |
| `0x13` | `0x02` | `+0x0b8` | `Boot_SetBootMode` |  |
| `0x13` | `0x03` | `+0x0bc` | `Boot_WarmReboot` |  |
| `0x13` | `0x0A` | `+0x0c0` | `Boot_GetDongleBootAudioMode` |  |
| `0x13` | `0x0B` | `+0x0c4` | `Boot_SetDongleBootAudioMode` |  |
| `0x14` | `0x01` | `+0x0a8` | `Output_ControlLed` |  |
| `0x14` | `0x06` | `+0x0ac` | `Output_SetBusyLightControl` |  |
| `0x14` | `0x07` | `+0x0b0` | `Output_GetBusyLightControl` |  |
| `0x17` | `0x03` | `+0x070` | `ANC_SetAdaptiveNoiseCancelationState` |  |
| `0x17` | `0x04` | `+0x074` | `ANC_GetAdaptiveNoiseCancelationState` | VERIFIED LIVE (ANC state=0/1) |
| `0x17` | `0x19` | `+0x078` | `ANC_SetAdjustableANCLevel` |  |
| `0x17` | `0x1A` | `+0x07c` | `ANC_GetAdjustableANCLevel` |  |
| `0x17` | `0x1B` | `+0x080` | `ANC_GetMaxAdjustableANCLevel` |  |
| `0x17` | `0x1C` | `+0x084` | `ANC_SetAdjustableHearThroughLevel` |  |
| `0x17` | `0x1D` | `+0x088` | `ANC_GetAdjustableHearThroughLevel` |  |
| `0x17` | `0x1E` | `+0x08c` | `ANC_GetMaxAdjustableHearThroughLevel` |  |
| `0x17` | `0x1F` | `+0x090` | `ANC_SetModeEx` |  |
| `0x17` | `0x20` | `+0x094` | `ANC_GetModeEx` |  |
| `0x17` | `0x21` | `+0x098` | `ANC_EnableDisableAdaptiveANC` |  |
| `0x17` | `0x22` | `+0x09c` | `ANC_GetAdaptiveANCStatus` |  |
| `0x17` | `0x23` | `+0x0a0` | `ANC_DisableHearThroughInCall` |  |
| `0x17` | `0x24` | `+0x0a4` | `ANC_GetDisableHearThroughInCallStatus` |  |
| `0x18` | `0x03` | `+0x068` | `Secure_ActivateNautilusBlacklisting` |  |
| `0x18` | `0x04` | `+0x06c` | `Secure_GetEncryptionState` |  |
| `0x19` | `0x01` | `+0x024` | `Upgrade_IsSupported` |  |
| `0x19` | `0x02` | `+0x028` | `Upgrade_Connect` |  |
| `0x19` | `0x03` | `+0x02c` | `(unnamed)` |  |
| `0x19` | `0x04` | `+0x030` | `Upgrade_Activate` |  |
| `0x19` | `0x05` | `+0x034` | `Upgrade_GetNumPartitionHandles` |  |
| `0x19` | `0x06` | `+0x038` | `Upgrade_GetPartitionHandle` |  |
| `0x19` | `0x07` | `+0x03c` | `Upgrade_GetPartitionInfo` |  |
| `0x19` | `0x08` | `+0x040` | `Upgrade_GetAvailablePartitionHandle` |  |
| `0x19` | `0x09` | `+0x044` | `Upgrade_GetActivationStatus` |  |
| `0x19` | `0x0A` | `+0x048` | `Upgrade_GetActivePartitionHandle` |  |
| `0x19` | `0x0B` | `+0x04c` | `Upgrade_GetUpgradeCapabilities` |  |
| `0x19` | `0x0C` | `+0x050` | `(unnamed)` |  |
| `0x19` | `0x0E` | `+0x054` | `Upgrade_ProcessData488` |  |
| `0x19` | `0x0F` | `+0x058` | `Upgrade_Claim` |  |
| `0x19` | `0x10` | `+0x05c` | `Upgrade_Release` |  |
| `0x19` | `0x11` | `+0x060` | `Upgrade_ProcessData232` |  |
| `0x19` | `0x12` | `+0x064` | `Upgrade_IsFirmwareCompatible` |  |
| `0x23` | `0x01` | `+0x018` | `Component_GetSubComponentList` |  |
| `0x23` | `0x02` | `+0x01c` | `Component_GetAllSubComponentsList` |  |
| `0x23` | `0x03` | `+0x020` | `Component_GetInfo` |  |
| `0x26` | `0x06` | `+0x014` | `Case_GetEarbudBdAddr` |  |
| `0x27` | `0x05` | `+0x00c` | `Stm_SetInterruptMusicState` |  |
| `0x27` | `0x06` | `+0x010` | `Stm_GetInterruptMusicState` |  |
